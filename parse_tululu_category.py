import os
import pathlib
import sys
from bs4 import BeautifulSoup
import requests
import argparse
from urllib.parse import urlsplit, urljoin
from time import sleep
from pathvalidate import sanitize_filename


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
        '--start_id',
        default=1,
        type=int,
        help='Cкачивать с страницы №',
    )
    parser.add_argument(
        '--end_id',
        default=5,
        type=int,
        help='Остановить на странице №',
    )
    parser.add_argument(
        '--genre',
        default='http://tululu.org/l55/',
        type=str,
        help='Указать ссылку на жанр книг',
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
    img_tag = soup.find('div', class_='bookimage').find('img')['src']
    genre_tag = soup.find('span', class_='d_book').find('a')['title']
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


def download_image(url, book_page_image):
    img_url = urljoin(url, book_page_image)
    folder_name = os.path.join('images', get_file_path(img_url))
    pathlib.Path('images').mkdir(parents=True, exist_ok=True)
    response = requests.get(img_url)
    response.raise_for_status()
    with open(folder_name, 'wb') as file:
        file.write(response.content)


def download_txt(book_page_title, book_content):
    book_name = sanitize_filename(book_page_title).strip()
    folder_name = os.path.join('books', f'{book_name}.txt')
    pathlib.Path('books').mkdir(parents=True, exist_ok=True)
    with open(folder_name, 'wb') as file:
        file.write(book_content)


def get_books_by_genre(url):
    url_genre_book = url
    response = requests.get(url_genre_book)
    response.raise_for_status()
    book_content = response.content
    # print(book_content)
    soup = BeautifulSoup(book_content, 'lxml')
    first_book = soup.find('a', class_='npage').text
    url_book_page = urljoin(url, first_book)
    print(url_book_page)

if __name__ == '__main__':
    url = 'https://tululu.org/'
    parsed_arguments = parse_arguments()
    if parsed_arguments.genre:
        print(parsed_arguments.genre)
        get_books_by_genre(parsed_arguments.genre)

    else:
        current_book_id = parsed_arguments.start_id
        while current_book_id <= parsed_arguments.end_id:
            try:
                book_html_content, book_content, book_url = get_book_by_id(url, current_book_id)
                book_properties = parse_book_page(book_html_content)
                download_txt(book_properties['title'], book_content)
                download_image(book_url, book_properties['book_image'])
                current_book_id += 1
            except requests.exceptions.HTTPError:
                print(f'Книга с ID {current_book_id} не существует')
                current_book_id += 1
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
                print("Отсутствие соединения, ожидание 5сек...", file=sys.stderr)
                sleep(5)
