import argparse
import asyncio
from dataclasses import dataclass

import orjson
from anyio import Path
from tqdm.asyncio import tqdm

from lubimyczytac import httpxClient


@dataclass
class NaKanapieBook:
    id: int
    bundleId: int
    bookId: int
    title: str
    authors: list[str]
    kind: str


@dataclass
class NaKanapieBooksPageResponse:
    books: list[NaKanapieBook]
    count: int
    pages: int


async def getBooksPage(username: str, page: int) -> NaKanapieBooksPageResponse:
    response = await httpxClient.post(
        url=f"https://nakanapie.pl/{username}/ksiazki/szukaj",
        json={
            "selectedLists": [],
            "selectedYears": [],
            "selectedSort": ["reading-stop", "desc"],
            "selectedSystemList": "all",
            "selectedSpecialLists": [],
            "page": page,
            "query": "",
            "perPage": 100,
            "update": 0,
        },
    )
    response.raise_for_status()
    data = response.json()
    return NaKanapieBooksPageResponse(
        books=[
            NaKanapieBook(
                id=book["id"],
                bundleId=book["bundle_id"],
                bookId=book["book_id"],
                title=book["title"],
                authors=book["authors"],
                kind=book["kind"],
            )
            for book in data["books"]
        ],
        count=data["pagination"]["count"],
        pages=data["pagination"]["pages"],
    )


async def getBooks(username: str) -> list[NaKanapieBook]:
    firstPage = await getBooksPage(username, 1)
    books = firstPage.books
    for booksPage in await tqdm.gather(
        *[getBooksPage(username, page) for page in range(2, firstPage.pages + 1)]
    ):
        books.extend(booksPage.books)
    return books


async def downloadNaKanapie(outputDirectory: Path, username: str):
    outputJson = outputDirectory / "nakanapie.json"
    books = await getBooks(username)
    await outputJson.write_bytes(orjson.dumps(books, option=orjson.OPT_INDENT_2))


async def main():
    parser = argparse.ArgumentParser(
        description="Program downloads books from nakanapie.pl"
    )
    parser.add_argument("username", type=str, help="Username from NaKanapie")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory",
        required=False,
        default=Path("."),
    )
    args = parser.parse_args()
    await downloadNaKanapie(outputDirectory=args.output, username=args.username)


if __name__ == "__main__":
    asyncio.run(main())
