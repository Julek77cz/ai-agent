from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio

app = FastAPI()

# Povolit CORS pro React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uchováváme všechny připojené WebSockety
connections = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Přijaté data z dashboardu: {data}")
            await websocket.send_text(f"Server obdržel: {data}")
    except:
        connections.remove(websocket)

# Funkce pro broadcast dat tasků všem připojeným dashboardům
async def broadcast_task(task_status: str):
    for conn in connections:
        try:
            await conn.send_text(task_status)
        except:
            connections.remove(conn)

# Simulace tasků pro test
async def simulate_tasks():
    i = 1
    while True:
        await asyncio.sleep(3)  # každé 3s nový status
        await broadcast_task(f"Task update #{i}")
        i += 1

# Spustit simulaci při startu serveru
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulate_tasks())
