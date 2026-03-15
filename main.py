import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.core.star import Star, Context
from astrbot.core.utils.io import download_file

from .lab_parser import LabParser


class Main(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.context = context
        self.base_dir = Path(__file__).parent / "data" / "lab_htmls"
        self._ensure_dir()

        self.binding_requests: Dict[str, float] = {}
        self.parser = LabParser(filter_keyword="大学物理实验")

        # 设定开学第一周的周一日期
        self.term_start_date = datetime(2026, 3, 2)

    def _ensure_dir(self):
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_current_week(self) -> int:
        """计算当前日期对应的教学周次"""
        now = datetime.now()
        delta = now - self.term_start_date
        # (天数 // 7) + 1 = 当前周
        current_week = (delta.days // 7) + 1
        return current_week

    @filter.command("绑定实验课表")
    async def bind_lab_schedule(self, event: AstrMessageEvent):
        """更新后的绑定提示词"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if not group_id:
            yield event.plain_result("❌ 请在群聊中使用此指令。")
            return

        self.binding_requests[f"{group_id}-{user_id}"] = time.time()

        # 按照你的要求更新提示词内容
        yield event.plain_result(
            "⏳ [实验课表绑定]\n"
            "请在 60 秒内直接发送导出的实验课表 .html 文件。\n"
            "html文件请电脑登录：\nhttps://etp.swjtu.edu.cn/user/yethan/index/student/studentList\n"
            "找到含有全部大物实验时间表的页面，按 'Ctrl+S' 导出。\n"
            "系统将自动识别其中“大学物理实验”相关的课程。"
        )

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_lab_file(self, event: AstrMessageEvent):
        """文件拦截处理"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        request_key = f"{group_id}-{user_id}"

        if request_key not in self.binding_requests: return
        if time.time() - self.binding_requests[request_key] > 60:
            del self.binding_requests[request_key]
            return

        file_component = next((m for m in event.get_messages() if hasattr(m, "type") and m.type == "File"), None)
        if not file_component: return

        save_path = self.base_dir / f"{group_id}_{user_id}.html"

        try:
            file_url = await file_component.get_file(allow_return_url=True)
            await download_file(file_url, str(save_path))

            with open(save_path, "r", encoding="utf-8") as f:
                content = f.read()
            courses = self.parser.parse(content)

            del self.binding_requests[request_key]
            if not courses:
                yield event.plain_result("✅ 文件已保存，但未识别到“大学物理实验”。")
            else:
                yield event.plain_result(
                    f"✅ 绑定成功！已识别到 {len(courses)} 节物理实验课。\n输入 /当前周实验 即可查看本周安排。")

        except Exception as e:
            logger.error(f"处理出错: {e}")
            yield event.plain_result(f"❌ 解析失败: {str(e)}")

    @filter.command("当前周实验")
    async def show_current_week_labs(self, event: AstrMessageEvent):
        """核心功能：显示当前周次的实验"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()

        file_path = self.base_dir / f"{group_id}_{user_id}.html"
        if not file_path.exists():
            yield event.plain_result("❓ 你还没有绑定过课表，请发送 /绑定实验课表")
            return

        current_week = self.get_current_week()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            all_courses = self.parser.parse(content)
            # 过滤出当前周的实验
            week_courses = [c for c in all_courses if c['week'] == current_week]

            if not week_courses:
                yield event.plain_result(f"📅 当前是第 {current_week} 周，本周你没有物理实验，好好休息吧！")
                return

            msg = f"📋 【{event.get_sender_name()}】第 {current_week} 周实验安排："
            for c in week_courses:
                msg += (f"\n\n星期{c['weekday']}\n"
                        f"🔹 实验：{c['project_name']}\n"
                        f"📍 地点：{c['location']}\n"
                        f"🕒 时间：{c['time_slot']}")

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"查询出错: {e}")
            yield event.plain_result("❌ 查询失败。")

    @filter.command("查看所有实验")
    async def show_all_labs(self, event: AstrMessageEvent):
        """原有功能：列出所有绑定的实验"""
        # ... 这里保持之前的 show_my_labs 逻辑 ...
        pass

    async def terminate(self):
        logger.info("Lab Binding plugin terminated.")