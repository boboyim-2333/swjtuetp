from bs4 import BeautifulSoup
import re
from typing import List, Dict


class LabParser:
    def __init__(self, filter_keyword: str = "大学物理实验"):
        self.filter_keyword = filter_keyword

    def parse(self, html_content: str) -> List[Dict]:
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', class_='el-table__row')

        results = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 12: continue

            course_name = cols[5].get_text(strip=True)
            if self.filter_keyword not in course_name: continue

            week_str = cols[9].get_text(strip=True)
            weekday_str = cols[10].get_text(strip=True)

            item = {
                "course_name": course_name,
                "project_name": cols[6].get_text(strip=True),
                "location": cols[7].get_text(strip=True),
                "week": int(week_str) if week_str.isdigit() else 0,  # 转为整数
                "weekday": int(weekday_str) if weekday_str.isdigit() else 0,
                "time_slot": cols[11].get_text(strip=True)
            }
            results.append(item)

        results.sort(key=lambda x: (x['week'], x['weekday']))
        return results