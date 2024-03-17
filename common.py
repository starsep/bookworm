from typing import Optional

import httpx
from bs4 import BeautifulSoup
from httpx import AsyncClient, Limits

httpxClient = AsyncClient(limits=Limits(max_connections=10))
httpxClient.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
)


def normalizeIsbn(isbn: str) -> str:
    return isbn.replace("-", "").replace(" ", "").strip()


async def getBookIsbn(url: str) -> Optional[str]:
    response = await httpxClient.get(url)
    if response.status_code == httpx.codes.NOT_FOUND:
        return None
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    isbnTag = soup.find("meta", {"property": "books:isbn"})
    if isbnTag is not None:
        isbn = isbnTag["content"]
        if isbn in ["000-00-0000-00-0"]:
            return None
        return normalizeIsbn(isbn)
    return None


def sortBooksByIsbn(books):
    return sorted(books, key=lambda book: "" if book.isbn is None else book.isbn)
