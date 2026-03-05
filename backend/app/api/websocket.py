import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class WebSocketManager:
    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = {}
        self.global_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, task_id: int | None = None):
        await websocket.accept()
        if task_id:
            self.connections.setdefault(task_id, set()).add(websocket)
        else:
            self.global_connections.add(websocket)

    def disconnect(self, websocket: WebSocket, task_id: int | None = None):
        if task_id and task_id in self.connections:
            self.connections[task_id].discard(websocket)
        self.global_connections.discard(websocket)

    async def broadcast(self, task_id: int, message: dict):
        data = json.dumps(message)
        targets = list(self.connections.get(task_id, set())) + list(self.global_connections)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                pass

    async def broadcast_state_change(self, task_id: int, old_status: str, new_status: str):
        await self.broadcast(task_id, {
            "type": "task_state_changed",
            "task_id": task_id,
            "data": {"old_status": old_status, "new_status": new_status},
        })


ws_manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, task_id: int | None = None):
    await ws_manager.connect(websocket, task_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id)
