import argparse
import asyncio
from pathlib import Path
from typing import Optional

from tqdm.asyncio import tqdm

from lubimyczytac import (
    readLubimyCzytac,
    downloadLubimyCzytac,
    LubimyCzytacBook,
    SHELF_READING,
    SHELF_READ,
    SHELF_WANT_TO_READ,
    SHELF_OWN,
)
from nakanapie import (
    readNaKanapie,
    downloadNaKanapie,
    NaKanapieBook,
    KIND_READING,
    KIND_READ,
    KIND_WANT_TO_READ,
    updateNaKanapieBookStatus,
    logInToNaKanapie,
    saveNaKanapie,
)

LUBIMYCZYTAC_TO_NAKANAPIE = {
    SHELF_READING: KIND_READING,
    SHELF_READ: KIND_READ,
    SHELF_WANT_TO_READ: KIND_WANT_TO_READ,
}


async def syncSharedBook(
    lubimyCzytacBook: LubimyCzytacBook, naKanapieBook: NaKanapieBook
):
    newKind = None
    newLists = []
    for shelf in lubimyCzytacBook.shelves:
        if shelf in LUBIMYCZYTAC_TO_NAKANAPIE:
            naKanapieExpected = LUBIMYCZYTAC_TO_NAKANAPIE[shelf]
            if isinstance(naKanapieExpected, str):
                if naKanapieBook.kind != naKanapieExpected:
                    newKind = naKanapieExpected
            elif isinstance(naKanapieExpected, int):
                if naKanapieExpected not in naKanapieBook.lists:
                    newLists.append(naKanapieExpected)
        else:
            print(f"Unknown LubimyCzytac shelf: {shelf}. Ignoring")
    if newKind is not None or len(newLists) > 0:
        naKanapieBook.kind = newKind
        naKanapieBook.lists.extend(newLists)
        await updateNaKanapieBookStatus(naKanapieBook)


async def syncSharedBooks(
    lubimyCzytacIsbnToBook: dict[str, LubimyCzytacBook],
    naKanapieIsbnToBook: dict[str, NaKanapieBook],
):
    sharedIsbns = set(lubimyCzytacIsbnToBook.keys()) & set(naKanapieIsbnToBook.keys())
    await tqdm.gather(
        *[
            syncSharedBook(lubimyCzytacIsbnToBook[isbn], naKanapieIsbnToBook[isbn])
            for isbn in sharedIsbns
        ]
    )


async def importLubimyCzytacToNaKanapie(
    profileIdLubimyCzytac: int,
    usernameNaKanapie: str,
    output: Path,
    forceDownload: bool,
    ownListId: Optional[int],
    loginNaKanapie: str,
    passwordNaKanapie: str,
):
    await logInToNaKanapie(userLogin=loginNaKanapie, userPassword=passwordNaKanapie)
    if ownListId is not None:
        LUBIMYCZYTAC_TO_NAKANAPIE[SHELF_OWN] = ownListId
    lubimyCzytacBooks = readLubimyCzytac(output)
    naKanapieBooks = readNaKanapie(output)
    if forceDownload or len(lubimyCzytacBooks) == 0:
        lubimyCzytacBooks = await downloadLubimyCzytac(output, profileIdLubimyCzytac)
    if forceDownload or len(naKanapieBooks) == 0:
        naKanapieBooks = await downloadNaKanapie(output, usernameNaKanapie)
    lubimyCzytacIsbnToBook = {
        book.isbn: book for book in lubimyCzytacBooks if book.isbn is not None
    }
    naKanapieIsbnToBook = {
        book.isbn: book for book in naKanapieBooks if book.isbn is not None
    }
    await syncSharedBooks(lubimyCzytacIsbnToBook, naKanapieIsbnToBook)
    saveNaKanapie(output, naKanapieBooks)


async def main():
    parser = argparse.ArgumentParser(
        description="Import books from lubimyczytac.pl to nakanapie.pl"
    )
    parser.add_argument(
        "profileIdLubimyCzytac", type=int, help="Profile id of LubimyCzytac user"
    )
    parser.add_argument("usernameNaKanapie", type=str, help="Username from NaKanapie")
    parser.add_argument("loginNaKanapie", type=str, help="Login to NaKanapie")
    parser.add_argument("passwordNaKanapie", type=str, help="Password to NaKanapie")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory",
        required=False,
        default=Path("."),
    )
    parser.add_argument(
        "--forceDownload",
        action="store_const",
        help="Whether to force downloading books info again",
        required=False,
        default=False,
    )
    parser.add_argument(
        "--ownListId",
        type=int,
        help="Id of the Owned list on NaKanapie",
        required=False,
        default=None,
    )
    args = parser.parse_args()
    await importLubimyCzytacToNaKanapie(
        profileIdLubimyCzytac=args.profileIdLubimyCzytac,
        usernameNaKanapie=args.usernameNaKanapie,
        loginNaKanapie=args.loginNaKanapie,
        passwordNaKanapie=args.passwordNaKanapie,
        output=args.output,
        forceDownload=args.forceDownload,
        ownListId=args.ownListId,
    )


if __name__ == "__main__":
    asyncio.run(main())
