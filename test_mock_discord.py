"""
Mock Discord Classes for Testing
===============================

This module provides mock Discord classes to test the security system
without requiring the full discord.py library to be installed.
"""

class MockInteraction:
    def __init__(self, user_id=123456789, guild_id=987654321):
        self.user = MockUser(user_id)
        self.guild = MockGuild(guild_id)
        self.response = MockInteractionResponse()
    
    async def response(self):
        return self.response

class MockUser:
    def __init__(self, user_id=123456789):
        self.id = user_id
        self.display_name = f"TestUser{user_id}"
        self.mention = f"<@{user_id}>"
        self.roles = []
    
    async def add_roles(self, role, reason=None):
        self.roles.append(role)
    
    async def send(self, embed=None, **kwargs):
        pass  # Mock sending DM

class MockGuild:
    def __init__(self, guild_id=987654321):
        self.id = guild_id
        self.members = []
    
    def get_role(self, role_id):
        return MockRole(role_id)
    
    async def fetch_member(self, user_id):
        return MockUser(user_id)

class MockRole:
    def __init__(self, role_id=1394786020842799235):
        self.id = role_id
        self.name = "Member"
        self.mention = f"<@&{role_id}>"

class MockInteractionResponse:
    async def send_message(self, content=None, embed=None, ephemeral=False):
        pass
    
    async def send_modal(self, modal):
        # Simulate modal submission
        modal.ingame_id.value = "RC463713"
        await modal.on_submit(MockInteraction())

class MockEmbed:
    def __init__(self, **kwargs):
        self.title = kwargs.get('title', '')
        self.description = kwargs.get('description', '')
        self.color = kwargs.get('color', 'blue')
        self.fields = []
    
    def add_field(self, name, value, inline=True):
        self.fields.append({'name': name, 'value': value, 'inline': inline})
    
    def set_footer(self, text, icon_url=None):
        self.footer = {'text': text, 'icon_url': icon_url}

class MockColor:
    @staticmethod
    def red():
        return "red"
    
    @staticmethod
    def green():
        return "green"
    
    @staticmethod
    def blue():
        return "blue"
    
    @staticmethod
    def orange():
        return "orange"

class MockMessage:
    def __init__(self, content="Test message with ID RC463713", author_id=123456789):
        self.content = content
        self.author = MockUser(author_id)
        self.channel = MockChannel()

class MockChannel:
    def __init__(self, name="car-sale-test"):
        self.name = name
        self.id = 1234567890
    
    async def send(self, embed=None, **kwargs):
        pass

# Create mock discord module
class MockDiscord:
    Interaction = MockInteraction
    Embed = MockEmbed
    Color = MockColor
    Message = MockMessage
    
    class ui:
        class Modal:
            def __init__(self, title="Mock Modal"):
                self.title = title
        
        class TextInput:
            def __init__(self, **kwargs):
                self.label = kwargs.get('label', '')
                self.placeholder = kwargs.get('placeholder', '')
                self.max_length = kwargs.get('max_length', 100)
                self.min_length = kwargs.get('min_length', 1)
                self.value = ""
    
    class app_commands:
        class CommandTree:
            def command(self, **kwargs):
                def decorator(func):
                    return func
                return decorator

def setup_mock_discord():
    """Setup mock discord for testing"""
    import sys
    sys.modules['discord'] = MockDiscord()
    return MockDiscord()

if __name__ == "__main__":
    # Test the mock classes
    mock = setup_mock_discord()
    print("Mock Discord classes created successfully")
    
    # Test interaction
    interaction = MockInteraction()
    print(f"Mock user: {interaction.user.display_name}")
    print(f"Mock guild ID: {interaction.guild.id}")
    
    # Test embed
    embed = MockEmbed(title="Test Embed", description="This is a test")
    print(f"Mock embed: {embed.title}")
    
    print("✅ All mock classes working correctly")