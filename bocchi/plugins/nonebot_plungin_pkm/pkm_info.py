

class PkmInfo:
    def __init__(self, name: str):
        self.name = name

    @classmethod
    async def get_info(cls):
        pass

    @classmethod
    async def get_pokemon_info(cls, pokemon_name: str):
        pass

    @classmethod
    async def get_skill_info(cls, skill_name: str):
        pass

    @classmethod
    async def get_ability_info(cls, ability_name: str):
        pass

    @classmethod
    async def get_item_info(cls, item_name: str):
        pass