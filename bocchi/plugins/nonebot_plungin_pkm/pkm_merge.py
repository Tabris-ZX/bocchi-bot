


class PkmMerge:
    def __init__(self, name1: str, name2: str):
        if name1 == name2:
            raise ValueError("两个宝可梦名称不能相同")
        self.name1 = name1
        self.name2 = name2

    @classmethod
    async def merge_pokemons(cls, name1: str, name2: str):
        pass