export interface SSEEvent {
    type: string;
    data: any;
}

export async function consumeSSEStream(
    response: Response,
    onEvent: (event: SSEEvent) => void,
    options?: { signal?: AbortSignal }
): Promise<void> {
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            if (options?.signal?.aborted) break;
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let currentEvent = '';
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6);
                    try {
                        const data = JSON.parse(dataStr);
                        onEvent({ type: currentEvent, data });
                    } catch {
                        // Non-JSON data (e.g., keep-alive comments)
                    }
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}
