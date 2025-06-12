from typing import Union

from fastapi import FastAPI
from pydantic import BaseModel


def create_app() -> FastAPI:
    """
    Factory function to create and configure the FastAPI application.
    This allows for better testing and modularity.
    """
    app = FastAPI()

    class Item(BaseModel):
        name: str
        price: float
        is_offer: bool | None = None

    @app.get("/")
    def read_root():
        return {"Hello": "World"}

    @app.get("/items/{item_id}")
    def read_item(item_id: int, q: str | None = None):
        return {"item_id": item_id, "q": q}

    @app.put("/items/{item_id}")
    def update_item(item_id: int, item: Item):
        return {"item_name": item.price, "item_id": item_id}

    return app
