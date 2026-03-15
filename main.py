import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List

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

        # 开学第一周周一：2026-03-02
        self.term_start_date = datetime(2026, 3, 2)

    def _ensure_dir(self):
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_current_week(self) -> int:
        now = datetime.now()
        delta = now - self.term_start_date
        return (delta.days // 7) + 1

    @filter.command("绑定实验课表")
    async def bind_lab_schedule(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if not group_id:
            yield event.plain_result("❌ 请在群聊中使用此指令。")
            return

        self.binding_requests[f"{group_id}-{user_id}"] = time.time()

        yield event.plain_result(
            "⏳ [实验课表绑定]\n"
            "请在 60 秒内直接发送导出的实验课表 .html 文件。\n"
            "html文件请电脑登录：https://etp.swjtu.edu.cn/user/yethan/index/student/studentList\n"
            "找到含有全部大物实验时间表的页面，按 'Ctrl+S' 导出。\n"
            "系统将自动识别其中“大学物理实验”相关的课程。"
        )

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_lab_file(self, event: AstrMessageEvent):
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
                yield event.plain_result("✅ 文件已保存，但未识别到“大学物理实验”内容。")
            else:
                yield event.plain_result(f"✅ 绑定成功！识别到 {len(courses)} 节实验。\n输入 /当前周实验 查看。")

        except Exception as e:
            logger.error(f"处理失败: {e}")
            yield event.plain_result(f"❌ 解析失败: {str(e)}")

    @filter.command("当前周实验")
    async def show_current_week_labs(self, event: AstrMessageEvent):
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

            # 1. 尝试找本周实验
            week_courses = [c for c in all_courses if c['week'] == current_week]

            if week_courses:
                msg = f"📋 【{event.get_sender_name()}】第 {current_week} 周实验安排："
                for c in week_courses:
                    msg += self._format_lab_info(c)
                yield event.plain_result(msg)
                return

            # 2. 本周没实验，找下一次实验
            next_labs = [c for c in all_courses if c['week'] > current_week]
            if next_labs:
                # 排序在 parser 中已做，取第一个即可
                next_lab = next_labs[0]
                msg = (f"📅 当前是第 {current_week} 周，本周你没有物理实验。\n\n"
                       f"🔍 帮你找到了下一次实验信息：\n"
                       f"📅 时间：第 {next_lab['week']} 周 星期{next_lab['weekday']}"
                       f"{self._format_lab_info(next_lab)}")
                yield event.plain_result(msg)
            else:
                yield event.plain_result(f"📅 当前是第 {current_week} 周，本学期所有的物理实验似乎都已经结束啦！")

        except Exception as e:
            logger.error(f"查询出错: {e}")
            yield event.plain_result("❌ 查询失败。")

    def _format_lab_info(self, c: Dict) -> str:
        """格式化单条实验信息"""
        return (f"\n--------------------\n"
                f"🔹 实验：{c['project_name']}\n"
                f"📍 地点：{c['location']}\n"
                f"🕒 时段：{c['time_slot']}")

    async def terminate(self):
        logger.info("Lab Binding plugin terminated.")