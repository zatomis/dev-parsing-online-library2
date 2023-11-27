import logging
import os
import pathlib
import sys
from os import path
from bs4 import BeautifulSoup
import requests
import argparse
from urllib.parse import urlsplit, urljoin
from time import sleep
from pathvalidate import sanitize_filename
import json


def check_for_redirect(response):
    """ Поднимает исключение HTTPError, если нет ответа с запрашиваемой страницы. """
    if response.history:
        raise requests.HTTPError


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Парсер библиотеки www.tululu.org"
    )
    parser.add_argument(
        '--skip_imgs',
        action='store_true',
        help='Cкачивать картинки',
    )
    parser.add_argument(
        '--skip_txt',
        action='store_true',
        help='Cкачивать книги',
    )
    parser.add_argument(
        '--genre',
        default='http://tululu.org/l55/',
        type=str,
        help='Указать ссылку на жанр книг',
    )
    parser.add_argument(
        '--dest_folder',
        default='General',
        type=str,
        help='Путь к каталогу с общими результатами парсинга: картинки, книги, JSON.',
    )
    parser.add_argument(
        '--start_page',
        default=1,
        type=int,
        help='Начальная страница для скачиваний',
    )
    parser.add_argument(
        '--end_page',
        default=2,
        type=int,
        help='Финальная страница для скачиваний',
    )
    args = parser.parse_args()
    return args


def get_file_path(url):
    path, filename = os.path.split(urlsplit(url).path)
    return filename


def parse_book_page(html_content):
    soup = BeautifulSoup(html_content, 'lxml')
    title_tag = soup.find('td', class_='ow_px_td').find('div').find('h1').text.split('::')
    book_name = str(title_tag[0]).replace('\\xa0', ' ').strip()
    book_author = str(title_tag[1]).replace('\\xa0', ' ').strip()
    img_tag = soup.select_one('div.bookimage').find('img')['src']
    genre_tag = soup.select_one('span.d_book a')['title']
    comments = [comment.text for comment in soup.select('.texts span')]
    book_id = soup.select_one('.r_comm input[name="bookid"]')['value']

    book_details = {
        "id": book_id,
        "title": sanitize_filename(book_name),
        "author": book_author,
        "comments": comments,
        "book_image": img_tag,
        "genre": genre_tag,
        "img_path": os.path.join('images', get_file_path(img_tag)),
        "book_path": os.path.join('books', f'{book_name.strip()}.txt')
    }
    return book_details


def get_book_by_id(url, book_id):
    url_book = f"{url}txt.php"
    params = {'id': book_id}
    response = requests.get(url_book, params)
    response.raise_for_status()
    book_content = response.content
    check_for_redirect(response=response)
    url = f"{url}b{book_id}/"
    response = requests.get(url)
    response.raise_for_status()
    check_for_redirect(response=response)
    return response.text, book_content, url


def download_image(url, path_to_the_image, general_folder):
    img_url = urljoin(url, path_to_the_image)
    folder_name = os.path.join(os.path.join(general_folder, 'images'), get_file_path(img_url))
    pathlib.Path(os.path.join(general_folder, 'images')).mkdir(parents=True, exist_ok=True)
    response = requests.get(img_url)
    response.raise_for_status()
    with open(folder_name, 'wb') as file:
        file.write(response.content)


def download_txt(book_page_title, book_content, general_folder):
    book_name = sanitize_filename(book_page_title).strip()
    folder_name = os.path.join(os.path.join(general_folder, 'books'), f'{book_name}.txt')
    pathlib.Path(os.path.join(general_folder, 'books')).mkdir(parents=True, exist_ok=True)
    with open(folder_name, 'wb') as file:
        file.write(book_content)


def get_total_pages(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'lxml')
    return int(soup.find_all('a', class_='npage')[5].text)


def get_book_ids_by_genre(url, start_page, end_page):
    books_page = get_total_pages(url)
    book_ids = []
    page_number = start_page
    total_page = min(books_page, end_page)
    while page_number <= total_page:
        try:
            url_page_book = urljoin(url, f"{page_number}/")
            response = requests.get(url_page_book)
            response.raise_for_status()
            books_page_content = response.content
        except requests.exceptions.HTTPError:
            print(f'Страница с книгой не существует')
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
            print("Отсутствие соединения, ожидание 5сек...", file=sys.stderr)
            sleep(5)
        else:
            soup = BeautifulSoup(books_page_content, 'lxml')
            books = soup.find_all('div', class_='bookimage')
            for book in books:
                book_tag = str(book).split('/b')[1]
                book_id = book_tag.split('/')[0]
                book_ids.append(book_id)
            page_number += 1
        return book_ids


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(filename)s:%(lineno)d - %(levelname)-8s - %(message)s'
    )

    logger = logging.getLogger(__name__)
    base_dir = path.dirname(path.abspath(__file__))

    url = 'https://tululu.org/'
    parsed_arguments = parse_arguments()
    general_folder = parsed_arguments.dest_folder
    books_descriptions = []
    book_id = 0
    book_ids = get_book_ids_by_genre(parsed_arguments.genre, parsed_arguments.start_page, parsed_arguments.end_page)
    for book_id in book_ids:
        try:
            book_html_content, book_content, book_url = get_book_by_id(url, book_id)
        except requests.exceptions.HTTPError:
            print(f'Книга с ID {book_id} не существует')
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
            print("Отсутствие соединения, ожидание 5сек...", file=sys.stderr)
            sleep(5)
        else:
            book_properties = parse_book_page(book_html_content)
            books_descriptions.append(book_properties)

            if not parsed_arguments.skip_txt:
                download_txt(book_properties['title'], book_content, general_folder)
            else:
                books_descriptions[-1]['book_path'] = ''
            if not parsed_arguments.skip_imgs:
                download_image(book_url, book_properties['book_image'], general_folder)
            else:
                books_descriptions[-1]['book_image'] = ''
                books_descriptions[-1]['img_path'] = ''

    if books_descriptions:
        pathlib.Path(general_folder).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(general_folder, 'descriptions.json'), 'w') as f:
            json.dump(books_descriptions, f, ensure_ascii=False)
