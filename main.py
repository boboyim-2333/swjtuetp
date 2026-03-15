import os
import time
from pathlib import Path
from typing import Dict

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.core.star import Star, Context
from astrbot.core.utils.io import download_file

# 导入刚才写的解析器
from .lab_parser import LabParser


class Main(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.context = context

        # 1. 自定义存储路径：插件目录/data/lab_htmls
        self.base_dir = Path(__file__).parent / "data" / "lab_htmls"
        self._ensure_dir()

        # 2. 状态机：记录发起绑定的用户 { "group_user": timestamp }
        self.binding_requests: Dict[str, float] = {}

        # 3. 初始化解析器
        self.parser = LabParser(filter_keyword="大学物理实验")

    def _ensure_dir(self):
        """确保存储目录存在"""
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    @filter.command("绑定实验课表")
    async def bind_lab_schedule(self, event: AstrMessageEvent):
        """指令触发：开启 60 秒文件接收窗口"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()

        if not group_id:
            yield event.plain_result("❌ 请在群聊中使用此指令。")
            return

        request_key = f"{group_id}-{user_id}"
        self.binding_requests[request_key] = time.time()

        yield event.plain_result(
            "⏳ [实验课表绑定]\n"
            "请在 60 秒内直接发送导出的实验课表 .html 文件。\n"
            "系统将自动识别其中“大学物理实验”相关的课程。"
        )

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_lab_file(self, event: AstrMessageEvent):
        """监听群消息，捕获绑定期间上传的 HTML 文件"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        request_key = f"{group_id}-{user_id}"

        # 1. 验证用户是否处于绑定状态
        if request_key not in self.binding_requests:
            return

        # 2. 检查是否超时
        if time.time() - self.binding_requests[request_key] > 60:
            del self.binding_requests[request_key]
            return

        # 3. 寻找消息中的文件组件
        file_component = next((m for m in event.get_messages() if hasattr(m, "type") and m.type == "File"), None)
        if not file_component:
            return

        # 4. 校验后缀
        file_name = getattr(file_component, "name", "unknown.html").lower()
        if not (file_name.endswith(".html") or file_name.endswith(".htm")):
            yield event.plain_result("⚠️ 格式错误！请上传 .html 文件，本次绑定已取消。")
            del self.binding_requests[request_key]
            return

        # 5. 设置保存路径
        save_path = self.base_dir / f"{group_id}_{user_id}.html"

        try:
            # 下载文件
            file_url = await file_component.get_file(allow_return_url=True)
            await download_file(file_url, str(save_path))

            if save_path.exists():
                # 读取并解析文件
                with open(save_path, "r", encoding="utf-8") as f:
                    content = f.read()

                courses = self.parser.parse(content)

                # 绑定成功，清理请求状态
                del self.binding_requests[request_key]

                if not courses:
                    yield event.plain_result("✅ 文件已保存，但未在其中找到任何“大学物理实验”课程。")
                else:
                    msg = f"✅ 实验课表绑定成功！\n共识别到 {len(courses)} 节物理实验课。"
                    # 预览最近的一节
                    recent = courses[0]
                    msg += f"\n\n最近实验预览：\n• 名称：{recent['project_name']}\n• 周次：第 {recent['week']} 周\n• 地点：{recent['location']}"
                    yield event.plain_result(msg)
            else:
                yield event.plain_result("❌ 文件保存失败，请检查网络或权限。")

        except Exception as e:
            logger.error(f"处理实验课表文件时出错: {e}")
            yield event.plain_result(f"❌ 解析过程中发生错误: {str(e)}")

    async def terminate(self):
        logger.info("Lab Binding plugin terminated.")