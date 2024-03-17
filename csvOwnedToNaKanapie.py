import argparse
import asyncio
import csv
from pathlib import Path

from tqdm.asyncio import tqdm

from nakanapie import (
    logInToNaKanapie,
    readNaKanapie,
    updateNaKanapieBookStatus,
    KIND_WANT_TO_READ,
    downloadNaKanapie,
)
from importLubimyCzytacToNaKanapie import addMissingBook


async def csvOwnedToNaKanapie(
    csvFile: Path, usernameNaKanapie: str, output: Path, ownListId: int
):
    dictReader = csv.DictReader(csvFile.open("r"))
    isbnColumn = next(
        filter(lambda column: "isbn" in column.lower(), dictReader.fieldnames)
    )
    books = {book.isbn: book for book in readNaKanapie(output)}
    missingNaKanapieIsbns = []
    isbnsToProcess = []
    for row in dictReader:
        isbnsToProcess.append(row[isbnColumn])

    async def processIsbn(isbn: str):
        if isbn not in books:
            await addMissingBook(isbn, KIND_WANT_TO_READ, missingNaKanapieIsbns)
        else:
            book = books[isbn]
            if ownListId not in book.lists:
                book.lists.append(ownListId)
                await updateNaKanapieBookStatus(book)

    await tqdm.gather(*[processIsbn(isbn) for isbn in isbnsToProcess])
    print("missingNaKanapieIsbns", missingNaKanapieIsbns)
    await downloadNaKanapie(output, usernameNaKanapie)


async def main():
    parser = argparse.ArgumentParser(
        description="Add books from CSV based on ISBN to owned list in nakanapie.pl"
    )
    parser.add_argument(
        "csvFile",
        type=Path,
        help="CSV File with ISBNs to add to owned list in nakanapie.pl",
    )
    parser.add_argument("ownListId", type=int, help="Id of the Owned list on NaKanapie")
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
    args = parser.parse_args()
    await logInToNaKanapie(
        userLogin=args.loginNaKanapie, userPassword=args.passwordNaKanapie
    )
    await csvOwnedToNaKanapie(
        csvFile=args.csvFile,
        usernameNaKanapie=args.usernameNaKanapie,
        output=args.output,
        ownListId=args.ownListId,
    )


if __name__ == "__main__":
    asyncio.run(main())
