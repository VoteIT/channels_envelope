from abc import ABC
from abc import abstractmethod
from typing import Set


class AsyncHandler(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def check(self) -> bool:
        ...

    @abstractmethod
    async def run(self):
        ...

    def __init__(self, message, **kwargs):
        self.kwargs = kwargs
        self.message = message
        self.valid = self.check()

    def __bool__(self):
        return self.valid

    def __init_subclass__(cls, **kwargs):
        cls.__registries = set()
        super().__init_subclass__(**kwargs)

    @classmethod
    def registries(cls) -> Set:
        return cls.__registries
