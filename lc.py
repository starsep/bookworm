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

    @property
    def bookId(self) -> int:
        return int(bookUrlPattern.search(self.url).group(1))


@dataclass
class BooksPageResponse:
    books: list[Book]
    count: int
    left: int


def getBooksPage(page: int, profileId: int) -> Optional[BooksPageResponse]:
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
        books.append(
            Book(
                coverUrl=cover[0]["data-src"],
                url=bookLink["href"],
                title=bookLink.text.strip(),
                author=authorLink.text.strip(),
                authorUrl=authorLink["href"],
                cycle=cycleLink.text.strip() if cycleLink is not None else None,
                cycleUrl=cycleLink["href"] if cycleLink is not None else None,
                shelves=[a.text.strip() for a in shelvesLinks],
            )
        )
    return BooksPageResponse(
        books=books,
        count=int(data["count"]),
        left=int(data["left"]),
    )


def getBooks(profileId: int) -> list[Book]:
    firstPage = getBooksPage(1, profileId)
    books = firstPage.books
    for page in tqdm(range(2, firstPage.count // len(firstPage.books) + 2)):
        pageBooks = getBooksPage(page, profileId)
        if pageBooks is None or len(pageBooks.books) == 0:
            break
        books.extend(pageBooks.books)
        page += 1
        if pageBooks.left <= 0:
            break
    return books


def downloadCovers(books: list[Book], outputDir: Path):
    outputDir.mkdir(exist_ok=True)
    for book in tqdm(books):
        outputCover = outputDir / f"{book.bookId}.jpg"
        if outputCover.exists():
            continue
        response = httpx.get(book.coverUrl)
        response.raise_for_status()
        with outputCover.open("wb") as f:
            f.write(response.content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Program downloads books and their covers from lubimyczytac.pl')
    parser.add_argument('profileId', type=int, help='Profile id of user')
    parser.add_argument('--output', type=Path, help='Output directory', required=False, default=Path("."))
    args = parser.parse_args()
    booksFetched = getBooks(args.profileId)
    outputDirectory: Path = args.output
    (outputDirectory / "lc.json").write_bytes(orjson.dumps(booksFetched))
    downloadCovers(booksFetched, outputDirectory / "covers")
