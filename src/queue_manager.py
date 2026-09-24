import asyncio
import logging

logger = logging.getLogger(__name__)

class DownloadQueue:
    def __init__(self, concurrency: int = 2):
        self.queue = asyncio.Queue()
        self.concurrency = concurrency
        self.workers = []

    async def start(self, process_func):
        """Avvia i worker che pescheranno dalla coda"""
        for i in range(self.concurrency):
            task = asyncio.create_task(self._worker(f"worker-{i}", process_func))
            self.workers.append(task)

    async def _worker(self, name, process_func):
        while True:
            job = await self.queue.get()
            try:
                logger.info(f"[{name}] Iniziando job: {job}")
                await process_func(job)
                logger.info(f"[{name}] Job completato: {job}")
            except Exception as e:
                logger.error(f"[{name}] Errore durante il job {job}: {e}")
            finally:
                self.queue.task_done()

    async def add_job(self, job_data):
        """Aggiunge un nuovo job alla coda"""
        await self.queue.put(job_data)
        
    async def stop(self):
        """Ferma tutti i worker (graceful shutdown)"""
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
