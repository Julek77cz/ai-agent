import asyncio
import websockets

async def test_ws():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as websocket:
        while True:
            msg = await websocket.recv()
            print("Přijaté z serveru:", msg)

asyncio.run(test_ws())
