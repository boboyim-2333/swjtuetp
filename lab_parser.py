from bs4 import BeautifulSoup
import re
from typing import List, Dict


class LabParser:
    def __init__(self, filter_keyword: str = "大学物理实验"):
        self.filter_keyword = filter_keyword

    def parse(self, html_content: str) -> List[Dict]:
        """
        解析 Element UI 表格并过滤包含特定关键字的课程
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        # 定位 Element UI 表格行
        rows = soup.find_all('tr', class_='el-table__row')

        results = []
        for row in rows:
            cols = row.find_all('td')
            # 确保列数足够（根据提供的 HTML，列数为 12）
            if len(cols) < 12:
                continue

            # 第 6 列是课程名 (索引为 5)
            course_name = cols[5].get_text(strip=True)

            # 过滤逻辑：只识别包含关键字的课程
            if self.filter_keyword not in course_name:
                continue

            # 提取数据
            item = {
                "course_name": course_name,
                "project_name": cols[6].get_text(strip=True),  # 项目名
                "location": cols[7].get_text(strip=True),  # 地点
                "teacher": cols[8].get_text(strip=True),  # 教师
                "week": cols[9].get_text(strip=True),  # 周次
                "weekday": cols[10].get_text(strip=True),  # 星期
                "time_slot": cols[11].get_text(strip=True)  # 时段 (如：下午B(16:30--19:30))
            }

            # 尝试从时段字符串中提取具体的起止时间
            time_match = re.search(r'(\d{2}:\d{2})--(\d{2}:\d{2})', item["time_slot"])
            if time_match:
                item["start_time"] = time_match.group(1)
                item["end_time"] = time_match.group(2)

            results.append(item)

        return results