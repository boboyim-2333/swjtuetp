from bs4 import BeautifulSoup
from typing import List, Dict


class LabParser:
    def __init__(self, filter_keyword: str = "大学物理实验"):
        self.filter_keyword = filter_keyword

    def parse(self, html_content: str) -> List[Dict]:
        """
        解析表格，提取所有包含关键字的行
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', class_='el-table__row')

        results = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 12: continue

            course_name = cols[5].get_text(strip=True)
            if self.filter_keyword not in course_name:
                continue

            w_str = cols[9].get_text(strip=True)
            wd_str = cols[10].get_text(strip=True)

            item = {
                "project_name": cols[6].get_text(strip=True),
                "location": cols[7].get_text(strip=True),
                "week": int(w_str) if w_str.isdigit() else 0,
                "weekday": int(wd_str) if wd_str.isdigit() else 0,
                "time_slot": cols[11].get_text(strip=True)
            }
            results.append(item)

        # 按时间排序
        results.sort(key=lambda x: (x['week'], x['weekday']))
        return results