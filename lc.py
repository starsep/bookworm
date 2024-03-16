import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import orjson
from bs4 import BeautifulSoup
import re

from tqdm import tqdm

bookUrlPattern = re.compile(r"/ksiazka/(\d+)")
authorUrlPattern = re.compile(r"/autor/(\d+)")
bookCycleUrlPattern = re.compile(r"/cykl/(\d+)")
shelvesUrlPattern = re.compile(r"/biblioteczka/lista\?shelfs=(\d+)")


@dataclass
class Book:
    coverUrl: str
    url: str
    title: str
    author: str
    authorUrl: str
    cycle: Optional[str]
    cycleUrl: Optional[str]
    shelves: list[str]
    isbn: Optional[str]

    @property
    def bookId(self) -> str:
        return bookUrlPattern.search(self.url).group(1)


@dataclass
class BooksPageResponse:
    books: list[Book]
    count: int
    left: int


def getBookIsbn(book: Book) -> Optional[str]:
    response = httpx.get(book.url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    isbnTag = soup.find("meta", {"property": "books:isbn"})
    if isbnTag is not None:
        isbn = isbnTag["content"]
        if isbn in ["000-00-0000-00-0"]:
            return None
        return isbn
    return None


def getBooksPage(
    page: int, profileId: int, bookIdToIsbn: dict[str, str]
) -> Optional[BooksPageResponse]:
    response = httpx.post(
        "https://lubimyczytac.pl/profile/getLibraryBooksList",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "cors",
        },
        data={
            "page": page,
            "listId": "booksFilteredList",
            "showFirstLetter": 0,
            "paginatorType": "Standard",
            "objectId": profileId,
            "own": 0,
        },
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()["data"]
    soup = BeautifulSoup(data["content"], "html.parser")
    books = []
    for row in soup.select("div.row"):
        if len(list(row.children)) <= 1:
            continue
        cover = row.select("img.img-fluid")
        if len(cover) == 0:
            continue
        bookLink = row.find("a", {"href": bookUrlPattern})
        authorLink = row.find("a", {"href": authorUrlPattern})
        cycleLink = row.find("a", {"href": bookCycleUrlPattern})
        shelvesLinks = row.find_all("a", {"href": shelvesUrlPattern})
        lcDomain = "https://lubimyczytac.pl"
        book = Book(
            coverUrl=cover[0]["data-src"],
            url=lcDomain + bookLink["href"]
            if lcDomain not in bookLink["href"]
            else bookLink["href"],
            title=bookLink.text.strip(),
            author=authorLink.text.strip(),
            authorUrl=authorLink["href"],
            cycle=cycleLink.text.strip() if cycleLink is not None else None,
            cycleUrl=cycleLink["href"] if cycleLink is not None else None,
            shelves=[a.text.strip() for a in shelvesLinks],
            isbn=None,
        )
        if book.bookId in bookIdToIsbn:
            book.isbn = bookIdToIsbn[book.bookId]
        if book.isbn is None:
            book.isbn = getBookIsbn(book)
        books.append(book)
    return BooksPageResponse(
        books=books,
        count=int(data["count"]),
        left=int(data["left"]),
    )


def getBooks(profileId: int, previousResult: list[Book]) -> list[Book]:
    bookIdToIsbn = {
        book.bookId: book.isbn for book in previousResult if book.isbn is not None
    }
    firstPage = getBooksPage(1, profileId, bookIdToIsbn)
    books = firstPage.books
    for page in tqdm(range(2, firstPage.count // len(firstPage.books) + 2)):
        pageBooks = getBooksPage(page, profileId, bookIdToIsbn)
        if pageBooks is None or len(pageBooks.books) == 0:
            break
        books.extend(pageBooks.books)
        page += 1
        if pageBooks.left <= 0:
            break
    return books


def downloadCovers(books: list[Book], coversDir: Path):
    coversDir.mkdir(exist_ok=True)
    for book in tqdm(books):
        coverPath = coversDir / f"{book.bookId}.jpg"
        if coverPath.exists():
            continue
        response = httpx.get(book.coverUrl)
        response.raise_for_status()
        with coverPath.open("wb") as f:
            f.write(response.content)


def main():
    parser = argparse.ArgumentParser(
        description="Program downloads books and their covers from lubimyczytac.pl"
    )
    parser.add_argument("profileId", type=int, help="Profile id of user")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory",
        required=False,
        default=Path("."),
    )
    args = parser.parse_args()
    outputDirectory: Path = args.output
    outputJson = outputDirectory / "lc.json"
    previousResult: list[Book] = []
    if outputJson.exists():
        with outputJson.open("rb") as f:
            previousResult = [Book(**book) for book in orjson.loads(f.read())]
    booksFetched = getBooks(args.profileId, previousResult)
    outputJson.write_bytes(orjson.dumps(booksFetched))
    downloadCovers(booksFetched, outputDirectory / "covers")


if __name__ == "__main__":
    main()
