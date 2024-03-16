from typing import Optional

import httpx
from bs4 import BeautifulSoup
from httpx import AsyncClient, Limits

httpxClient = AsyncClient(limits=Limits(max_connections=10))


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
