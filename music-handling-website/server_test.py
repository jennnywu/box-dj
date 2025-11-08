import asyncio
import websockets

HOST = "0.0.0.0"
PORT = 12345

async def handler(websocket):
    print("Client connected")
    try:
        async for message in websocket:
            print(f"Received message: {message}")
            await websocket.send("Pi: got it")
    except websockets.ConnectionClosed:
        print("Client disconnected")

async def main():
    async with websockets.serve(handler, HOST, PORT):
        print(f"WebSocket server running on ws://{HOST}:{PORT}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())