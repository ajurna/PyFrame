from asyncio import QueueShutDown
from pathlib import PurePosixPath, Path
from typing import Annotated, Any, Awaitable

import aiodav.exceptions
from pydantic import BeforeValidator, Field
from aiodav import Client
from pydantic_settings import BaseSettings, SettingsConfigDict, CliApp, YamlConfigSettingsSource, \
    PydanticBaseSettingsSource
import asyncio
from loguru import logger
from tempfile import TemporaryFile
class Validators:
    @staticmethod
    def lowercase_list(value: list[str]) -> list:
        return [i.lower() for i in value]

class WebdavSettings(BaseSettings):
    host: str
    username: str
    password: str
    target_dirs: list[PurePosixPath]
    workers: int = 10

class FilterSettings(BaseSettings):
    ignore_files: Annotated[list, BeforeValidator(Validators.lowercase_list)] = Field(default_factory=list)
    ignore_files_contains: Annotated[list, BeforeValidator(Validators.lowercase_list)] = Field(default_factory=list)
    ignore_folders: Annotated[list, BeforeValidator(Validators.lowercase_list)] = Field(default_factory=list)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file="nextcloud.yaml"
    )
    webdav: WebdavSettings
    destination: Path = Field(default_factory=Path)
    filters: FilterSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls),)

class NextcloudDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Client = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.prefix = PurePosixPath(f"/remote.php/dav/files/{settings.webdav.username}")

    @logger.catch
    async def run(self):
        worker_tasks = []
        for _ in range(self.settings.webdav.workers):
            task = asyncio.create_task(self.download_worker())
            worker_tasks.append(task)


        self.client = Client(self.settings.webdav.host, login=self.settings.webdav.username, password=self.settings.webdav.password)
        for directory in self.settings.webdav.target_dirs:
            await self.process_directory(PurePosixPath(self.prefix, directory), self.settings.destination)
        await self.queue.join()
        self.queue.shutdown()
        await self.client.close()

    @logger.catch
    async def download_worker(self):
        logger.debug(f"Starting download worker")
        destination = None
        try:
            while True:
                try:
                    source, destination = await self.queue.get()
                    await self.client.download_file(source, destination)
                    logger.info(f"Finished downloading {destination}")
                    destination = None
                    self.queue.task_done()
                except aiodav.exceptions.WebDavException as e:
                    if destination:
                        Path(destination).unlink()
                    logger.error(f"Error while downloading file: {e}")
                    self.queue.task_done()
        except QueueShutDown:
            logger.debug("Worker ShutDown")
            return

    @logger.catch
    async def process_directory(self, source: PurePosixPath, destination: Path) -> None:
        logger.debug(f"Checking destination {destination}")
        if not destination.exists():
            destination.mkdir()
        logger.debug(f"Processing directory: {source}")
        work_items = []
        directory_list = await self.client.list(str(source), get_info=True)
        for item in directory_list:
            item_path = PurePosixPath(item["path"])
            if self.item_filtered(item,  item_path):
                if item['isdir']:
                    logger.info(f"Directory {item['path']}")
                    work_items.append(
                        self.log_awaitable_finish(self.process_directory(item_path, Path(destination, item_path.name)), f"Finished processing directory {item_path}")
                    )
                else:
                    file_destination = Path(destination, item_path.name)
                    if file_destination.exists():
                        logger.info(f"File exists:  {file_destination}")
                    else:
                        logger.info(f"Queueing download {file_destination}")
                        self.queue.put_nowait((item["path"], str(file_destination)))
            else:
                logger.info(f"ignoring item {item["path"]}")
        await asyncio.gather(*work_items)


    async def log_awaitable_finish(self, download: Awaitable, log_line: str):
        await download
        logger.debug(log_line)

    @logger.catch
    def item_filtered(self, item: dict[str, str], item_path: PurePosixPath) -> bool:
        file_name =item_path.name.lower()
        if item['isdir']:
            if file_name in self.settings.filters.ignore_folders:
                return False
        else:
            if file_name in self.settings.filters.ignore_files:
                return False
            elif any(fn in file_name for fn in self.settings.filters.ignore_files_contains):
                return False
        return True


if __name__ == "__main__":
    try:
        config = CliApp.run(Settings)
    except Exception as err:
        print(f"Error loading settings: {err}")
        exit(1)
    print(config.model_dump())
    downloader = NextcloudDownloader(config)
    asyncio.run(downloader.run())