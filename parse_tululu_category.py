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
    """
    Поднимает исключение HTTPError, если ответ с не запрашиваемой страницы.
    """
    if response.history:
        raise requests.HTTPError


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Парсер библиотеки www.tululu.org"
    )
    parser.add_argument(
        '--skip_imgs',
        default=False,
        type=bool,
        help='Cкачивать картинки',
    )
    parser.add_argument(
        '--skip_txt',
        default=True,
        type=bool,
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
        '--page_limit',
        default=2,
        type=int,
        help='Ограничить число страниц при скачивании жанра книг',
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
    # img_tag = soup.find('div', class_='bookimage').find('img')['src']
    img_tag = soup.select_one('div.bookimage').find('img')['src']
    # genre_tag = soup.find('span', class_='d_book').find('a')['title']
    genre_tag = soup.select_one('span.d_book a')['title']
    comments = [comment.text for comment in soup.select('.texts span')]
    book_id = soup.select_one('.r_comm input[name="bookid"]')['value']

    serialized_book = {
        "id": book_id,
        "title": sanitize_filename(book_name),
        "author": book_author,
        "comments": comments,
        "book_image": img_tag,
        "genre": genre_tag,
        "img_path": os.path.join('img', get_file_path(img_tag)),
        "book_path": os.path.join('books', f'{book_name.strip()}.txt')
    }
    return serialized_book


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


def download_image(url, book_page_image, general_folder):
    img_url = urljoin(url, book_page_image)
    if len(general_folder):
        pathlib.Path(general_folder).mkdir(parents=True, exist_ok=True)
        os.chdir(general_folder)
    folder_name = os.path.join('images', get_file_path(img_url))
    pathlib.Path('images').mkdir(parents=True, exist_ok=True)
    response = requests.get(img_url)
    response.raise_for_status()
    with open(folder_name, 'wb') as file:
        file.write(response.content)


def download_txt(book_page_title, book_content, general_folder):
    book_name = sanitize_filename(book_page_title).strip()
    if len(general_folder):
        pathlib.Path(general_folder).mkdir(parents=True, exist_ok=True)
        os.chdir(general_folder)
    folder_name = os.path.join('books', f'{book_name}.txt')
    pathlib.Path('books').mkdir(parents=True, exist_ok=True)
    with open(folder_name, 'wb') as file:
        logger.info(f'Загрузка - {folder_name}')
        file.write(book_content)


def get_book_id_by_genre(url, page_limit):
    response = requests.get(url)
    response.raise_for_status()
    books_page_content = response.content
    soup = BeautifulSoup(books_page_content, 'lxml')
    books_page = int(soup.find_all('a', class_='npage')[5].text)
    books_id = []
    page = 1
    while page <= books_page:
        url_book_page = urljoin(url, str(page))
        response = requests.get(url_book_page)
        response.raise_for_status()
        books_page_content = response.content
        soup = BeautifulSoup(books_page_content, 'lxml')
        books = soup.find_all('div', class_='bookimage')
        for book in books:
            books_id.append(str(str(book).split('/b')[1]).split('/')[0])
        page += 1
        if page > page_limit:
            break
        return books_id

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
    descriptions_of_books = []
    try:
        books_id = get_book_id_by_genre(parsed_arguments.genre, parsed_arguments.page_limit)
        descriptions_of_books = []
        for book_id in books_id:
            book_html_content, book_content, book_url = get_book_by_id(url, book_id)
            book_properties = parse_book_page(book_html_content)
            descriptions_of_books.append(book_properties)
            if (parsed_arguments.skip_txt):
                os.chdir(base_dir)
                download_txt(book_properties['title'], book_content, general_folder)
            else:
                descriptions_of_books[-1]['book_path'] = ''
            if (parsed_arguments.skip_imgs):
                os.chdir(base_dir)
                download_image(book_url, book_properties['book_image'], general_folder)
            else:
                descriptions_of_books[-1]['book_image'] = ''
                descriptions_of_books[-1]['img_path'] = ''


    except requests.exceptions.HTTPError:
        print(f'Книга с ID {book_id} не существует')
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
        print("Отсутствие соединения, ожидание 5сек...", file=sys.stderr)
        sleep(5)

    if descriptions_of_books:
        os.chdir(general_folder)
        with open('descriptions.json', 'w') as f:
            json.dump(descriptions_of_books, f, ensure_ascii=False)
