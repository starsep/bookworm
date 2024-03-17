import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import orjson
from bs4 import BeautifulSoup
import re

from tqdm.asyncio import tqdm
from common import httpxClient, normalizeIsbn, getBookIsbn, sortBooksByIsbn

bookUrlPattern = re.compile(r"/ksiazka/(\d+)")
authorUrlPattern = re.compile(r"/autor/(\d+)")
bookCycleUrlPattern = re.compile(r"/cykl/(\d+)")
shelvesUrlPattern = re.compile(r"/biblioteczka/lista\?shelfs=(\d+)")

lubimyCzytacDomain = "https://lubimyczytac.pl"

SHELF_READ = "Przeczytane"
SHELF_OWN = "Posiadam"
SHELF_WANT_TO_READ = "Chcę przeczytać"
SHELF_READING = "Teraz czytam"


@dataclass
class LubimyCzytacBook:
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
class LubimyCzytacBooksPageResponse:
    books: list[LubimyCzytacBook]
    count: int
    left: int


async def getBooksPage(
    page: int, profileId: int, bookIdToIsbn: dict[str, str]
) -> Optional[LubimyCzytacBooksPageResponse]:
    response = await httpxClient.post(
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
    if response.status_code == httpx.codes.NOT_FOUND:
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
        book = LubimyCzytacBook(
            coverUrl=cover[0]["data-src"],
            url=lubimyCzytacDomain + bookLink["href"]
            if lubimyCzytacDomain not in bookLink["href"]
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
        books.append(book)
    return LubimyCzytacBooksPageResponse(
        books=books,
        count=int(data["count"]),
        left=int(data["left"]),
    )


async def getBooks(
    profileId: int, previousResult: list[LubimyCzytacBook]
) -> list[LubimyCzytacBook]:
    bookIdToIsbn = {
        book.bookId: normalizeIsbn(book.isbn)
        for book in previousResult
        if book.isbn is not None
    }
    firstPage = await getBooksPage(1, profileId, bookIdToIsbn)
    books = firstPage.books

    async def _processPage(page: int):
        pageBooks = await getBooksPage(page, profileId, bookIdToIsbn)
        if pageBooks is None or len(pageBooks.books) == 0:
            return
        books.extend(pageBooks.books)
        page += 1

    await tqdm.gather(
        *[
            _processPage(page)
            for page in range(2, firstPage.count // len(firstPage.books) + 2)
        ],
        desc="📖 LubimyCzytac: Downloading books",
    )

    async def _addMissingIsbn(book: LubimyCzytacBook):
        book.isbn = await getBookIsbn(book.url)

    await tqdm.gather(
        *[_addMissingIsbn(book) for book in books if book.isbn is None],
        desc="📖 LubimyCzytac: Adding missing ISBNs",
    )
    return books


async def downloadCovers(books: list[LubimyCzytacBook], coversDir: Path):
    coversDir.mkdir(exist_ok=True)

    async def _downloadCover(book: LubimyCzytacBook):
        coverPath = coversDir / f"{book.bookId}.jpg"
        if coverPath.exists():
            return
        response = await httpxClient.get(book.coverUrl)
        response.raise_for_status()
        with coverPath.open("wb") as f:
            f.write(response.content)

    await tqdm.gather(
        *[_downloadCover(book) for book in books],
        desc="📖 LubimyCzytac: Downloading covers",
    )


def readLubimyCzytac(outputDirectory: Path) -> list[LubimyCzytacBook]:
    outputJson = outputDirectory / "lubimyczytac.json"
    result: list[LubimyCzytacBook] = []
    if outputJson.exists():
        with outputJson.open("rb") as f:
            result = [LubimyCzytacBook(**book) for book in orjson.loads(f.read())]
    return result


async def downloadLubimyCzytac(
    outputDirectory: Path, profileId: int
) -> list[LubimyCzytacBook]:
    outputJson = outputDirectory / "lubimyczytac.json"
    previousResult = readLubimyCzytac(outputDirectory)
    booksFetched = await getBooks(profileId, previousResult)
    outputJson.write_bytes(
        orjson.dumps(sortBooksByIsbn(booksFetched), option=orjson.OPT_INDENT_2)
    )
    await downloadCovers(booksFetched, outputDirectory / "covers")
    return booksFetched


async def main():
    parser = argparse.ArgumentParser(
        description="Program downloads books info and their covers from lubimyczytac.pl"
    )
    parser.add_argument("profileId", type=int, help="Profile id of LubimyCzytac user")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory",
        required=False,
        default=Path("."),
    )
    args = parser.parse_args()
    await downloadLubimyCzytac(outputDirectory=args.output, profileId=args.profileId)


if __name__ == "__main__":
    asyncio.run(main())
