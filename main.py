"""
Simple FastAPI backend with DynamoDB storage, deployable as an AWS Lambda function.

Endpoints:
    POST   /items          -> create an item
    GET    /items           -> list all items
    GET    /items/{item_id} -> get one item
    PUT    /items/{item_id} -> update an item
    DELETE /items/{item_id} -> delete an item
    GET    /health          -> health check

Local run:
    uvicorn main:app --reload

Lambda:
    The `handler` object at the bottom is the Lambda entry point
    (set as the Lambda handler: main.handler).
"""

import os
import uuid
import time
from typing import Optional, List

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from mangum import Mangum

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TABLE_NAME = os.environ.get("TABLE_NAME", "items")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

# ---------------------------------------------------------------------------
# App
# ----------------------------------A-----------------------------------------

app = FastAPI(title="Items API", version="1.0.0")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)


class Item(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: int
    updated_at: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/items", response_model=Item, status_code=201)
def create_item(payload: ItemCreate):
    now = int(time.time())
    item = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "description": payload.description,
        "created_at": now,
        "updated_at": now,
    }
    try:
        table.put_item(Item=item)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return item


@app.get("/items", response_model=List[Item])
def list_items():
    try:
        response = table.scan()
        items = response.get("Items", [])
        # handle pagination for large tables
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return items


@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: str):
    try:
        response = table.get_item(Key={"id": item_id})
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))
    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.put("/items/{item_id}", response_model=Item)
def update_item(item_id: str, payload: ItemUpdate):
    try:
        response = table.get_item(Key={"id": item_id})
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

    existing = response.get("Item")
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")

    updates = payload.dict(exclude_unset=True)
    existing.update(updates)
    existing["updated_at"] = int(time.time())

    try:
        table.put_item(Item=existing)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return existing


# @app.delete("/items/{item_id}", status_code=204)
# def delete_item(item_id: str):
#     try:
#         response = table.get_item(Key={"id": item_id})
#         if not response.get("Item"):
#             raise HTTPException(status_code=404, detail="Item not found")
#         table.delete_item(Key={"id": item_id})
#     except ClientError as e:
#         raise HTTPException(status_code=500, detail=str(e))
#     return None




# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

handler = Mangum(app)