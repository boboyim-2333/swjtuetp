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

        # 路径设置：插件目录/data/lab_htmls
        self.base_dir = Path(__file__).parent / "data" / "lab_htmls"
        self._ensure_dir()

        self.binding_requests: Dict[str, float] = {}
        self.parser = LabParser(filter_keyword="大学物理实验")

        # 教学周设定：2026年3月2日为第一周周一
        self.term_start_date = datetime(2026, 3, 2)

    def _ensure_dir(self):
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_current_week(self) -> int:
        """计算当前周次"""
        now = datetime.now()
        delta = now - self.term_start_date
        return (delta.days // 7) + 1

    @filter.command("绑定实验课表")
    async def bind_lab_schedule(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        self.binding_requests[user_id] = time.time()

        yield event.plain_result(
            "⏳ [实验课表绑定]\n"
            "请在 60 秒内直接发送导出的实验课表 .html 文件。\n"
            "html文件请电脑登录：https://etp.swjtu.edu.cn/user/yethan/index/student/studentList\n"
            "找到含有全部大物实验时间表的页面，按 'Ctrl+S' 导出。\n"
            "系统将自动识别其中“大学物理实验”相关的课程。"
        )

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_lab_file(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()

        if user_id not in self.binding_requests: return
        if time.time() - self.binding_requests[user_id] > 60:
            del self.binding_requests[user_id]
            return

        file_component = next((m for m in event.get_messages() if hasattr(m, "type") and m.type == "File"), None)
        if not file_component: return

        # 文件名与 QQ 号绑定，实现数据隔离
        save_path = self.base_dir / f"lab_{user_id}.html"

        try:
            file_url = await file_component.get_file(allow_return_url=True)
            await download_file(file_url, str(save_path))

            if save_path.exists():
                # 校验一次解析是否成功（即便不强校验学号，也要确认能读到物理实验）
                with open(save_path, "r", encoding="utf-8") as f:
                    courses = self.parser.parse(f.read())

                del self.binding_requests[user_id]

                yield event.plain_result(
                    f"✅ 绑定成功！\n"
                    f"📁 文件保存路径：\n{save_path.absolute()}\n"
                    f"📊 识别到物理实验共 {len(courses)} 节。\n"
                    f"输入 /当前周实验 即可查询。"
                )

        except Exception as e:
            logger.error(f"绑定失败: {e}")
            yield event.plain_result(f"❌ 绑定出错: {str(e)}")

    @filter.command("当前周实验")
    async def show_current_week_labs(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        file_path = self.base_dir / f"lab_{user_id}.html"

        if not file_path.exists():
            yield event.plain_result("❓ 你还没有绑定过课表，请发送 /绑定实验课表")
            return

        current_week = self.get_current_week()
        now = datetime.now()
        current_weekday = now.weekday() + 1  # 1-7

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                all_labs = self.parser.parse(f.read())

            # 1. 查找本周实验
            this_week = [c for c in all_labs if c['week'] == current_week]

            if this_week:
                msg = f"📋 【{event.get_sender_name()}】第 {current_week} 周实验安排："
                for c in this_week:
                    msg += self._format_lab(c)
                yield event.plain_result(msg)
            else:
                # 2. 查找下一次实验：周次大于当前周，或者本周内还没到的实验
                next_labs = [c for c in all_labs if
                             c['week'] > current_week or (c['week'] == current_week and c['weekday'] > current_weekday)]

                if next_labs:
                    nxt = next_labs[0]
                    msg = (f"当前sender_id{event.get_sender_id}"
                           f"正在查询{user_id}...."
                           f"📅 当前是第 {current_week} 周，本周你没有物理实验。\n\n"
                           f"🔍 帮你预告下一次实验：\n"
                           f"📅 时间：第 {nxt['week']} 周 星期{nxt['weekday']}"
                           f"{self._format_lab(nxt)}")
                    yield event.plain_result(msg)
                else:
                    yield event.plain_result(f"🎉 厉害了！本学期的物理实验已经全部修完啦！")

        except Exception as e:
            logger.error(f"查询出错: {e}")
            yield event.plain_result("❌ 查询失败。")

    def _format_lab(self, c: Dict) -> str:
        return (f"\n--------------------\n"
                f"🔹 项目：{c['project_name']}\n"
                f"📍 地点：{c['location']}\n"
                f"🕒 时段：{c['time_slot']}")

    async def terminate(self):
        logger.info("Lab Binding plugin terminated.")