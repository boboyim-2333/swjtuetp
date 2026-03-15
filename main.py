import os
import time
from pathlib import Path
from typing import Dict
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.core.star import Star, Context
from astrbot.core.utils.io import download_file


class Main(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.context = context

        # 1. 手动定义存储路径：插件同级目录下的 data/lab_files
        self.base_dir = Path(__file__).parent / "data" / "lab_files"
        self._ensure_dir()

        # 记录请求状态：{ "group_id-user_id": timestamp }
        self.binding_requests: Dict[str, float] = {}

    def _ensure_dir(self):
        """确保存储文件夹存在"""
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"已创建实验课表存储目录: {self.base_dir}")

    @filter.command("绑定实验课表")
    async def bind_lab_schedule(self, event: AstrMessageEvent):
        """指令触发：开始绑定流程"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()

        if not group_id:
            yield event.plain_result("❌ 请在群聊中使用此指令。")
            return

        # 记录请求
        request_key = f"{group_id}-{user_id}"
        self.binding_requests[request_key] = time.time()

        yield event.plain_result(
            "⏳ [实验课表绑定]\n"
            "请在 60 秒内发送实验课表的 .html 文件。\n"
            "系统会自动识别并保存。"
        )

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_file_upload(self, event: AstrMessageEvent):
        """监听群消息：捕获上传的文件"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if not group_id or not user_id:
            return

        request_key = f"{group_id}-{user_id}"

        # 1. 检查是否存在有效的绑定请求
        if request_key not in self.binding_requests:
            return

        # 2. 检查是否超时
        start_time = self.binding_requests[request_key]
        if time.time() - start_time > 60:
            del self.binding_requests[request_key]
            # 悄悄过期，不干扰群聊，除非用户再次输入指令
            return

        # 3. 提取文件组件
        file_component = next((m for m in event.get_messages() if hasattr(m, "type") and m.type == "File"), None)
        if not file_component:
            return

        # 4. 校验文件后缀（简单检查）
        file_name = getattr(file_component, "name", "unknown.html").lower()
        if not (file_name.endswith(".html") or file_name.endswith(".htm")):
            yield event.plain_result("⚠️ 检测到文件，但不是 .html 格式，绑定取消。")
            del self.binding_requests[request_key]
            return

        # 5. 生成保存路径：文件名格式为 group_user.html
        save_path = self.base_dir / f"{group_id}_{user_id}.html"

        try:
            # 获取下载链接
            file_url = await file_component.get_file(allow_return_url=True)
            if not file_url or not str(file_url).startswith("http"):
                yield event.plain_result("❌ 无法获取文件下载链接，请重试。")
                return

            # 下载文件
            await download_file(file_url, str(save_path))

            if save_path.exists():
                logger.info(f"实验课表已存至: {save_path}")
                del self.binding_requests[request_key]
                yield event.plain_result(f"✅ 实验课表绑定成功！\n文件已保存至本地：{save_path.name}")
            else:
                yield event.plain_result("❌ 文件保存失败。")

        except Exception as e:
            logger.error(f"绑定实验课表出错: {e}")
            yield event.plain_result(f"❌ 出错啦: {str(e)}")

    async def terminate(self):
        logger.info("Lab Binding plugin terminated.")