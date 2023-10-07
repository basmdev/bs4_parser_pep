import logging
import re
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, MAIN_PEP_URL
from outputs import control_output
from utils import find_tag, get_response


def pep(session):
    response = get_response(session, MAIN_PEP_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features="lxml")
    numerical_index = find_tag(soup, "section", attrs={"id": "numerical-index"})
    tbody = find_tag(numerical_index, "tbody")
    tr_tags = tbody.find_all("tr")
    pep_count = 0
    status_count = {}
    results = [("Статус", "Количество")]
    for tr_tag in tqdm(tr_tags):
        pep_count += 1
        status = tr_tag.find("td").text[1:]
        if status in EXPECTED_STATUS:
            status_full = EXPECTED_STATUS[status]
        else:
            status_full = []
            logging.info(f"В списке неверный статус: {status}" f"В строке: {tr_tag}")
        link = tr_tag.find("a")["href"]
        link_full = urljoin(MAIN_PEP_URL, link)
        response = get_response(session, link_full)
        soup = BeautifulSoup(response.text, features="lxml")
        dl_class = find_tag(soup, "dl")
        page_status = dl_class.find(string="Status")
        if page_status:
            page_status_parent = page_status.find_parent()
            final_status = page_status_parent.next_sibling.next_sibling.string
            if final_status not in status_full:
                logging.info(
                    f"Не совпадают статусы: {link_full}"
                    f"На странице {final_status}, а в списке {status_full}"
                )
            if final_status in status_count:
                status_count[final_status] += 1
            else:
                status_count[final_status] = 1
        else:
            logging.error(f"На странице {link_full} нет статуса")
            continue
    results.extend(status_count.items())
    results.append(("Total", pep_count))
    return results


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, "whatsnew/")
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features="lxml")
    main_div = find_tag(soup, "section", attrs={"id": "what-s-new-in-python"})
    div_with_ul = find_tag(main_div, "div", attrs={"class": "toctree-wrapper"})
    sections_by_python = div_with_ul.find_all("li", attrs={"class": "toctree-l1"})

    results = [("Ссылка на статью", "Заголовок", "Редактор, Автор")]
    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, "a")
        version_link = urljoin(whats_new_url, version_a_tag["href"])
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, "lxml")
        h1 = find_tag(soup, "h1")
        dl = find_tag(soup, "dl")
        dl_text = dl.text.replace("\n", " ")
        results.append((version_link, h1.text, dl_text))

    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features="lxml")
    sidebar = find_tag(soup, "div", attrs={"class": "sphinxsidebarwrapper"})
    ul_tags = sidebar.find_all("ul")
    for ul in ul_tags:
        if "All versions" in ul.text:
            a_tags = ul.find_all("a")
            break
    else:
        raise Exception("Ничего не нашлось")
    results = [("Ссылка на документацию", "Версия", "Статус")]
    pattern = r"Python (?P<version>\d\.\d+) \((?P<status>.*)\)"
    for a_tag in a_tags:
        link = a_tag["href"]
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ""
        results.append((link, version, status))
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, "download.html")
    response = get_response(session, downloads_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features="lxml")
    table_tag = find_tag(soup, "table", {"class": "docutils"})
    pdf_a4_tag = find_tag(table_tag, "a", {"href": re.compile(r".+pdf-a4\.zip$")})
    pdf_a4_link = pdf_a4_tag["href"]
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split("/")[-1]
    downloads_dir = BASE_DIR / "downloads"
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)
    with open(archive_path, "wb") as file:
        file.write(response.content)
    logging.info(f"Архив был загружен и сохранён: {archive_path}")


MODE_TO_FUNCTION = {
    "whats-new": whats_new,
    "latest-versions": latest_versions,
    "download": download,
    "pep": pep,
}


def main():
    configure_logging()
    logging.info("Парсер запущен!")
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f"Аргументы командной строки: {args}")
    session = requests_cache.CachedSession()

    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info("Парсер завершил работу.")


if __name__ == "__main__":
    main()
