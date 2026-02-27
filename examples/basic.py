from typing import Annotated

from pydantic import BaseModel

from barq import Barq
from barq import Depends
from barq import HTTPException
from barq import Response

app = Barq()


class Item(BaseModel):
    name: str
    price: float
    quantity: int = 1


class ItemResponse(BaseModel):
    id: int
    name: str
    price: float
    quantity: int


items_db: dict[int, Item] = {}
next_id = 1


def get_db() -> dict[int, Item]:
    return items_db


@app.get("/")
def index() -> dict[str, str]:
    return {"message": "Welcome to Barq!"}


@app.get("/items")
def list_items(db: Annotated[dict[int, Item], Depends(get_db)]) -> list[ItemResponse]:
    return [
        ItemResponse(id=item_id, **item.model_dump())
        for item_id, item in db.items()
    ]


@app.get("/items/{item_id}")
def get_item(
    item_id: int,
    db: Annotated[dict[int, Item], Depends(get_db)],
) -> ItemResponse:
    if item_id not in db:
        raise HTTPException(404, "Item not found")
    item = db[item_id]
    return ItemResponse(id=item_id, **item.model_dump())


@app.post("/items")
def create_item(
    body: Item,
    db: Annotated[dict[int, Item], Depends(get_db)],
) -> ItemResponse:
    global next_id
    item_id = next_id
    next_id += 1
    db[item_id] = body
    return ItemResponse(id=item_id, **body.model_dump())


@app.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    db: Annotated[dict[int, Item], Depends(get_db)],
) -> Response:
    if item_id not in db:
        raise HTTPException(404, "Item not found")
    del db[item_id]
    return Response.empty()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.on_startup
def startup() -> None:
    print("Application starting up...")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=4)
