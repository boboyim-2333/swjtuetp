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
        # 存储路径：插件同级目录/data/lab_htmls
        self.base_dir = Path(__file__).parent / "data" / "lab_htmls"
        self._ensure_dir()

        self.binding_requests: Dict[str, float] = {}
        self.parser = LabParser(filter_keyword="大学物理实验")

        # 校准开学日期：2026年3月2日（周一）
        self.term_start_date = datetime(2026, 3, 2)

    def _ensure_dir(self):
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_current_week(self) -> int:
        """计算当前是第几周"""
        now = datetime.now()
        delta = now - self.term_start_date
        # 计算间隔周数，不足7天为第1周
        return (delta.days // 7) + 1

    @filter.command("绑定实验课表")
    async def bind_lab_schedule(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if not group_id:
            yield event.plain_result("❌ 请在群聊中使用此指令。")
            return

        # 使用 group+user 唯一标识请求
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

        # 校验请求是否存在且未超时
        if request_key not in self.binding_requests: return
        if time.time() - self.binding_requests[request_key] > 60:
            del self.binding_requests[request_key]
            return

        file_component = next((m for m in event.get_messages() if hasattr(m, "type") and m.type == "File"), None)
        if not file_component: return

        # 每个用户拥有独立的文件名
        save_path = self.base_dir / f"{group_id}_{user_id}.html"

        try:
            file_url = await file_component.get_file(allow_return_url=True)
            await download_file(file_url, str(save_path))

            if save_path.exists():
                with open(save_path, "r", encoding="utf-8") as f:
                    content = f.read()
                courses = self.parser.parse(content)

                del self.binding_requests[request_key]

                # 绑定成功反馈：显示绝对路径
                abs_path = save_path.absolute()
                msg = (f"✅ 绑定成功！\n"
                       f"📁 文件保存路径：\n{abs_path}\n"
                       f"📊 识别到 {len(courses)} 节物理实验课。\n"
                       f"输入 /当前周实验 即可查看。")
                yield event.plain_result(msg)
            else:
                yield event.plain_result("❌ 文件下载失败。")

        except Exception as e:
            logger.error(f"解析失败: {e}")
            yield event.plain_result(f"❌ 绑定出错: {str(e)}")

    @filter.command("当前周实验")
    async def show_current_week_labs(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        user_id = event.get_sender_id()  # 严格获取当前发送者的 ID

        # 动态寻找当前用户对应的文件
        file_path = self.base_dir / f"{group_id}_{user_id}.html"

        if not file_path.exists():
            yield event.plain_result(f"❓ 【{event.get_sender_name()}】你还没有绑定过课表，请发送 /绑定实验课表")
            return

        current_week = self.get_current_week()
        now = datetime.now()
        current_weekday = now.weekday() + 1  # 1-7

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            all_courses = self.parser.parse(content)

            # 1. 查找本周实验
            week_courses = [c for c in all_courses if c['week'] == current_week]

            if week_courses:
                msg = f"📋 【{event.get_sender_name()}】第 {current_week} 周实验安排："
                for c in week_courses:
                    msg += self._format_lab_info(c)
                yield event.plain_result(msg)
            else:
                # 2. 本周没课，找下一次（周次大于当前周，或本周剩余时间）
                next_labs = [c for c in all_courses if
                             c['week'] > current_week or (c['week'] == current_week and c['weekday'] > current_weekday)]

                if next_labs:
                    next_lab = next_labs[0]
                    msg = (f"📅 当前是第 {current_week} 周，本周你没有物理实验啦。\n\n"
                           f"🔍 帮你预告下一次实验：\n"
                           f"📅 时间：第 {next_lab['week']} 周 星期{next_lab['weekday']}"
                           f"{self._format_lab_info(next_lab)}")
                    yield event.plain_result(msg)
                else:
                    yield event.plain_result(f"📅 第 {current_week} 周：本学期的物理实验已经全部结束了！")

        except Exception as e:
            logger.error(f"查询失败: {e}")
            yield event.plain_result("❌ 查询出错。")

    def _format_lab_info(self, c: Dict) -> str:
        """格式化单条实验输出"""
        return (f"\n--------------------\n"
                f"🔹 实验：{c['project_name']}\n"
                f"📍 地点：{c['location']}\n"
                f"🕒 时段：{c['time_slot']}")

    async def terminate(self):
        logger.info("Lab Binding plugin terminated.")