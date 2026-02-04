import React, { useState, useEffect } from 'react';
import io from 'socket.io-client';

const socket = io('http://localhost:8000'); // Python backend WebSocket

function TaskStatus() {
    const [status, setStatus] = useState([]);

    useEffect(() => {
        socket.on('task_update', (data) => {
            setStatus(prev => [...prev, data]);
        });
    }, []);

    return (
        <div>
            {status.map((s, i) => (
                <div key={i}>{s}</div>
            ))}
        </div>
    );
}

export default TaskStatus;
