import re
import os
import time
import asyncio
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import readchar
from rich.console import Console

console = Console()


class InteractiveMenu:
    def __init__(self):
        self.items = []
        self.selected_index = 0

    def add_item(self, label: str, value):
        self.items.append({"label": label, "value": value})

    def render(self):
        console.clear()
        for i, item in enumerate(self.items):
            prefix = "→ " if i == self.selected_index else "  "
            style = "bold white on blue" if i == self.selected_index else "white"
            console.print(f"{prefix}{item['label']}", style=style)
        console.print("\n[dim]使用 ↑ ↓ 方向键选择,回车确认,ESC 返回[/dim]")

    def show(self):
        if not self.items:
            return None
        self.selected_index = 0
        while True:
            self.render()
            key = readchar.readkey()
            if key == readchar.key.UP:
                self.selected_index = (self.selected_index - 1) % len(self.items)
            elif key == readchar.key.DOWN:
                self.selected_index = (self.selected_index + 1) % len(self.items)
            elif key == readchar.key.ENTER or key == "\r":
                return self.items[self.selected_index]
            elif key == readchar.key.ESC:
                return None


class SearchResultSelector:
    @staticmethod
    def show_search_results(results: List[Dict], keyword: str):
        if not results:
            console.print("[red]❌ 未找到搜索结果[/red]")
            return None
        selected_index = 0
        while True:
            console.clear()
            for i, result in enumerate(results):
                prefix = f"[{i+1}] "
                style = "bold white on blue" if i == selected_index else "white"
                console.print(f"{prefix}{result['title']}", style=style)
            result = results[selected_index]
            console.print("\n[bold]详细信息：[/bold]")
            console.print(f"  [dim]ID:[/dim] {result['id']}")
            console.print(f"  [yellow]作者: {result['author']}[/yellow]")
            console.print(f"  [green]状态: {result['status']}[/green]")
            console.print(f"  [cyan]字数: {result['word_count']}[/cyan]")
            if result["description"]:
                desc_preview = result["description"]
                console.print(f"  [dim]简介: {desc_preview}[/dim]")
            console.print("\n[dim]使用 ↑ ↓ 方向键选择,回车确认,ESC 返回[/dim]")
            key = readchar.readkey()
            if key == readchar.key.UP:
                selected_index = (selected_index - 1) % len(results)
            elif key == readchar.key.DOWN:
                selected_index = (selected_index + 1) % len(results)
            elif key == readchar.key.ENTER or key == "\r":
                return results[selected_index]
            elif key == readchar.key.ESC:
                return None


class ChapterRangeSelector:
    @staticmethod
    def show_range_selector(total_chapters: int):
        console.clear()
        menu = InteractiveMenu()
        menu.add_item("爬取全部章节", ("all", 1, total_chapters))
        menu.add_item("爬取指定章节范围", ("custom", None, None))
        menu.add_item("退出", ("exit", None, None))
        choice = menu.show()
        if not choice or choice["value"][0] == "exit":
            return None, None
        mode, start, end = choice["value"]
        if mode == "all":
            return start, end
        console.clear()
        console.print("[cyan]自定义章节范围[/cyan]\n")
        try:
            start_chapter = int(input(f"请输入起始章节 (1-{total_chapters}): ").strip())
            if start_chapter < 1 or start_chapter > total_chapters:
                console.print("[red]❌ 起始章节无效[/red]")
                return None, None
            end_chapter = input(
                f"请输入结束章节 ({start_chapter}-{total_chapters}) [默认全部]: "
            ).strip()
            if end_chapter:
                end_chapter = int(end_chapter)
                if end_chapter < start_chapter or end_chapter > total_chapters:
                    console.print("[red]❌ 结束章节无效[/red]")
                    return None, None
            else:
                end_chapter = total_chapters
            return start_chapter, end_chapter
        except ValueError:
            console.print("[red]❌ 请输入有效的数字[/red]")
            return None, None


class ConfirmationDialog:
    @staticmethod
    def show_confirmation(title: str, message: str) -> bool:
        menu = InteractiveMenu(title)
        menu.add_item("确认 (Y)", True)
        menu.add_item("取消 (N)", False)
        console.print(f"[yellow]{message}[/yellow]\n")
        choice = menu.show()
        return choice["value"] if choice else False


class ProgressBar:
    @staticmethod
    def show_success(message: str):
        console.print(f"[green]✓ {message}[/green]")

    @staticmethod
    def show_error(message: str):
        console.print(f"[red]✗ {message}[/red]")


def show_main_menu():
    menu = InteractiveMenu()
    menu.add_item("📚 搜索小说", "search")
    menu.add_item("🔢 直接输入小说ID", "input")
    menu.add_item("❌ 退出", "exit")
    choice = menu.show()
    return choice["value"] if choice else None


base_url_template = "https://www.xpxs.net/index/{}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_page(url: str, retry: int = 3) -> str:
    for attempt in range(retry):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(1)
            else:
                console.print(f"[red]获取页面失败: {url}, 错误: {e}[/red]")
                raise


def extract_page_info(html: str, novel_id: str):
    soup = BeautifulSoup(html, "html.parser")
    pages = []
    seen_urls = set()
    select_element = soup.find("select", {"id": "indexselect"})
    if select_element:
        options = select_element.find_all("option")
        for idx, option in enumerate(options, 1):
            value = option.get("value", "").strip()
            text = option.text.strip()
            match = re.search(r"(\d+)\s*-\s*(\d+)\s*章", text)
            if match and value:
                start_chapter = int(match.group(1))
                end_chapter = int(match.group(2))
                full_url = f"https://www.xpxs.net{value}"
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    pages.append(
                        {
                            "index": idx,
                            "start_chapter": start_chapter,
                            "end_chapter": end_chapter,
                            "url": full_url,
                            "text": text,
                        }
                    )
    title_element = soup.find("title")
    novel_title = title_element.text.strip() if title_element else f"Novel_{novel_id}"
    title_match = re.search(r"^(.*?)最新章节目录", novel_title)
    if title_match:
        novel_title = title_match.group(1).strip()
    return pages, novel_title


def parse_chapter_list(html: str, page_start_index: int):
    soup = BeautifulSoup(html, "html.parser")
    chapters = []
    links = soup.find_all("a", href=re.compile(r"/chapter/"))
    for idx, link in enumerate(links):
        title = link.text.strip()
        href = link.get("href", "").strip()
        if title and href:
            full_url = (
                href if href.startswith("http") else f"https://www.xpxs.net{href}"
            )
            chapters.append(
                {"index": page_start_index + idx, "title": title, "url": full_url}
            )
    return chapters


def search_novels(keyword: str):
    search_url = f"https://www.xpxs.net/search/?searchkey={keyword}"
    try:
        html = fetch_page(search_url)
        soup = BeautifulSoup(html, "html.parser")
        results = []
        dl_elements = soup.find_all("dl")
        for dl in dl_elements:
            title_link = dl.find("dt")
            if not title_link:
                continue
            title_a = title_link.find("a")
            if not title_a:
                continue
            title = title_a.get("title", "").strip() or title_a.text.strip()
            href = title_a.get("href", "").strip()
            novel_id_match = re.search(r"/book/(\d+)/", href)
            if not novel_id_match:
                continue
            novel_id = novel_id_match.group(1)
            dd_elements = dl.find_all("dd")
            description = ""
            author = ""
            status = ""
            word_count = ""
            for dd in dd_elements:
                text = dd.get_text(strip=True)
                author_a = dd.find("a")
                if author_a and (
                    author_a.get("href", "").startswith("/author/")
                    or "连载" in text
                    or "全本" in text
                ):
                    author = author_a.text.strip()
                    spans = dd.find_all("span")
                    if len(spans) >= 1:
                        status = spans[0].text.strip()
                    if len(spans) >= 2:
                        word_count = spans[1].text.strip()
                elif text and len(text) > 20:
                    description = text
            results.append(
                {
                    "id": novel_id,
                    "title": title,
                    "author": author,
                    "status": status,
                    "word_count": word_count,
                    "description": description,
                }
            )
        return results
    except Exception as e:
        console.print(f"[red]❌ 搜索失败: {e}[/red]")
        return []


def clean_content(text: str, chapter_title: str = "") -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"<[^>]*>", "", cleaned)
    # 需要批量剔除的内容正则
    patterns = [
        r"虾皮小说【.*?】.*?最新章节[。]?",
        r"本章未完.*?下一页.*?阅读[。]?",
        r"章节报错.*?免登录[。]?",
        r".*?请大家收藏.*?更新速度.*?最快[。]?",
    ]
    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned)
    if chapter_title:
        title_pattern = rf"^\s*{re.escape(chapter_title)}\s*"
        if re.match(title_pattern, cleaned, re.MULTILINE):
            cleaned = re.sub(title_pattern, "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s+|\s+$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"^\s*[─=\*]{5,}\s*$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


async def parse_chapter_content(
    chapter_index: int, chapter_title: str, chapter_url: str, retry: int = 3
) -> str:
    all_content = []
    current_page = chapter_url
    page_number = 1
    for attempt in range(retry):
        try:
            while current_page:
                html = fetch_page(current_page)
                soup = BeautifulSoup(html, "html.parser")
                content_selectors = [
                    "#booktxt",
                    ".content",
                    "#content",
                    ".chapter-content",
                    ".novel-content",
                ]
                page_content = ""
                for selector in content_selectors:
                    element = soup.select_one(selector)
                    if element:
                        page_content = element.get_text()
                        break
                if page_content:
                    cleaned = clean_content(page_content, chapter_title)
                    if cleaned:
                        all_content.append(cleaned)
                        if page_number > 1:
                            console.print(f"\t- 继续获取第 {page_number} 页...")
                next_button = soup.find("a", {"rel": "next"})
                if next_button:
                    next_href = next_button.get("href", "")
                    if next_href and re.search(r"_\d+\.html$", next_href):
                        current_page = (
                            f"https://www.xpxs.net{next_href}"
                            if next_href.startswith("/")
                            else next_href
                        )
                        page_number += 1
                        time.sleep(0.1)
                    else:
                        current_page = None
                else:
                    current_page = None
            break
        except Exception as e:
            if attempt < retry - 1:
                await asyncio.sleep(0.1)
            else:
                console.print(f"\t第 {page_number} 页获取失败: {e}")
                break
    combined_content = "\n\n".join(all_content)
    formatted_title = f"第 {chapter_index} 章 {chapter_title}"
    return f"{formatted_title}\n\n{combined_content}"


def get_pages_and_title(novel_id: str):
    base_url = base_url_template.format(novel_id)
    console.print("[yellow]正在获取分页信息...[/yellow]\n")
    first_page_html = fetch_page(f"{base_url}/")
    pages, novel_title = extract_page_info(first_page_html, novel_id)
    if not pages:
        console.print("[red]❌ 未找到分页信息,请检查小说ID是否正确[/red]")
        return [], novel_title
    console.print(f"找到 {len(pages)} 个分页：")
    for page in pages:
        console.print(
            f"\t第{page['index']}页: {page['start_chapter']} - {page['end_chapter']}章"
        )
    console.print()
    return pages, novel_title


async def scrape_novel(start_chapter: int, end_chapter: int, novel_title: str, pages):
    # 只爬取用户选择的章节范围
    # 先构建章节索引和url列表
    chapters_to_scrape = []
    for page in pages:
        for idx in range(page["start_chapter"], page["end_chapter"] + 1):
            if start_chapter <= idx <= end_chapter:
                chapters_to_scrape.append(
                    {
                        "index": idx,
                        "title": f"第{idx}章",  # 标题可后续优化为真实标题
                        "url": page["url"].replace(
                            "index", f"chapter/{idx}"
                        ),  # 构造章节url
                    }
                )
    if not chapters_to_scrape:
        console.print("[red]❌ 没有找到任何章节[/red]")
        return
    console.print(f"\n[yellow]开始爬取 {len(chapters_to_scrape)} 个章节...[/yellow]\n")
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    results = await asyncio.gather(
        *[
            parse_chapter_content(chap["index"], chap["title"], chap["url"])
            for chap in chapters_to_scrape
        ]
    )
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"《{novel_title}》\n")
        f.write(f"{'=' * 50}\n\n")
        success_count = 0
        fail_count = 0
        for i, (_, content) in enumerate(zip(chapters_to_scrape, results)):
            progress = f"[{i + 1}/{len(chapters_to_scrape)}]"
            if content.strip():
                f.write("\n\n" + content)
                f.flush()
                ProgressBar.show_success(f"{progress} 已写入文件 ({len(content)} 字符)")
                success_count += 1
            else:
                ProgressBar.show_error(f"{progress} 失败: 内容为空")
                fail_count += 1
    console.print()
    console.print(
        f"[bold green]✓ 爬取完成![/bold green]\n\n成功: [green]{success_count}[/green] 章\n失败: [red]{fail_count}[/red] 章\n文件: [cyan]{output_file}[/cyan]",
    )


if __name__ == "__main__":
    while True:
        choice = show_main_menu()
        if not choice or choice == "exit":
            console.print("[yellow]👋 再见![/yellow]")
            break
        novel_id = novel_title = ""
        if choice == "search":
            console.print("\n[cyan]请输入搜索关键词:[/cyan] ", end="")
            keyword = input().strip()
            if not keyword:
                console.print("[red]❌ 搜索关键词不能为空![/red]")
                continue
            results = search_novels(keyword)
            if not results:
                console.print("[red]❌ 未找到相关小说[/red]\n按任意键继续...")
                readchar.readkey()
                continue
            selected = SearchResultSelector.show_search_results(results, keyword)
            if not selected:
                continue
            novel_id = selected["id"]
            novel_title = selected["title"]
        elif choice == "input":
            console.print("\n[cyan]请输入小说ID:[/cyan] ", end="")
            novel_id = input().strip()
            if not novel_id:
                console.print("[red]❌ 小说ID不能为空![/red]")
                continue
        pages, novel_title = get_pages_and_title(novel_id)
        if not pages:
            console.print("[red]❌ 无法获取章节信息,请检查小说ID[/red]")
            readchar.readkey()
            continue
        start_chapter, end_chapter = ChapterRangeSelector.show_range_selector(
            max(page["end_chapter"] for page in pages)
        )
        if not start_chapter or not end_chapter:
            continue
        global output_file
        output_file = f"novels/{re.sub(r'[<>:"/\\|?*]', "", novel_title)}_{start_chapter}-{end_chapter}.txt"
        if not ConfirmationDialog.show_confirmation(
            "确认开始爬取？", "按回车确认开始爬取,ESC 取消"
        ):
            console.print("[yellow]已取消[/yellow]")
            continue
        console.print()
        asyncio.run(scrape_novel(start_chapter, end_chapter, novel_title, pages))
        console.print("\n[green]按任意键返回主菜单...[/green]")
        readchar.readkey()
