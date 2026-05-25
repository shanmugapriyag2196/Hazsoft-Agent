from config import PDF_FOLDER, QDRANT_COLLECTION
from rag import index_chunks


def main() -> None:
    count = index_chunks(PDF_FOLDER)
    print(f"Indexed {count} chunks into Qdrant collection '{QDRANT_COLLECTION}'.")


if __name__ == "__main__":
    main()
