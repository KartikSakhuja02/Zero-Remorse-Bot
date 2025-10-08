import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import logging
from scrim_highlights import ScrimHighlightModal, setup_scrim_highlights

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)

class MatchFormatView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
    
    @discord.ui.select(
        placeholder="Select match format...",
        options=[
            discord.SelectOption(label="BO1 - Best of 1", value="BO1"),
            discord.SelectOption(label="BO2 - Best of 2", value="BO2"),
            discord.SelectOption(label="BO3 - Best of 3", value="BO3"),
            discord.SelectOption(label="BO4 - Best of 4", value="BO4"),
            discord.SelectOption(label="BO5 - Best of 5", value="BO5"),
        ]
    )
    async def select_match_format(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_format = select.values[0]
        
        # Store the selected format for this user
        if not hasattr(interaction.client, 'user_match_formats'):
            interaction.client.user_match_formats = {}
        interaction.client.user_match_formats[self.user_id] = selected_format
        
        # Ask for clan name
        clan_embed = discord.Embed(
            title="Scrim Highlight Upload",
            description=f"**Step 2: Enter Clan Name**\n\n"
                       f"Match Format: **{selected_format}** (Best of {selected_format[2]})\n\n"
                       f"**Please type the name of the clan you played against:**\n"
                       f"Just send a message with the clan name.\n\n"
                       f"**Example:**\n"
                       f"*Team Liquid*",
            color=0xffa500
        )
        clan_embed.set_footer(text="Zero Remorse • Waiting for clan name...")
        
        await interaction.response.edit_message(embed=clan_embed, view=None)

class UploadHighlightView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
    
    @discord.ui.button(
        label="Upload Scrim Highlight", 
        style=discord.ButtonStyle.primary,
        custom_id="upload_highlight_btn"
    )
    async def upload_highlight(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the upload scrim highlight button click"""
        # Check if user has the Valom role using role ID
        valom_role_id = int(os.getenv('VALOM_ROLE_ID'))
        has_valom_role = any(role.id == valom_role_id for role in interaction.user.roles)
        
        if not has_valom_role:
            # User doesn't have Valom role
            await interaction.response.send_message(
                "**Access Denied**\n\nYou don't have the required **Valom** role to upload scrim highlights.",
                ephemeral=True
            )
            return
        
        # User has Valom role - send DM with dropdown
        try:
            dm_embed = discord.Embed(
                title="Scrim Highlight Upload",
                description="**Step 1: Select Match Format**\n\n"
                           "Please select what type of match this highlight is from using the dropdown below.",
                color=0x9d4edd
            )
            dm_embed.set_footer(text="Zero Remorse • Scrim Highlights System")
            
            # Create the view with dropdown
            view = MatchFormatView(interaction.user.id)
            await interaction.user.send(embed=dm_embed, view=view)
            
            # Confirm in the channel (ephemeral)
            await interaction.response.send_message(
                "**Check your DMs!**\n\n"
                "I've sent you instructions for uploading your scrim highlight. "
                "Please send your screenshot/video in our DM conversation.",
                ephemeral=True
            )
            
        except discord.Forbidden:
            # User has DMs disabled
            await interaction.response.send_message(
                "**Cannot send DM**\n\n"
                "Please enable DMs from server members so I can send you upload instructions.\n"
                "Go to: **Server Settings → Privacy Settings → Allow direct messages from server members**",
                ephemeral=True
            )

class ZeroRemorseBot(commands.Bot):
    def __init__(self):
        # Use only basic intents to avoid privileged intent requirements
        intents = discord.Intents.default()
        intents.message_content = False  # Don't need privileged message content intent
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        
        super().__init__(
            command_prefix=os.getenv('BOT_PREFIX', '!'),
            intents=intents,
            case_insensitive=True
        )
        
        self.guild_id = int(os.getenv('GUILD_ID'))
        self.channel_id = int(os.getenv('CHANNEL_ID'))
    
    async def setup_hook(self):
        """This is called when the bot starts up"""
        # Add the persistent view
        self.add_view(UploadHighlightView())
        
        # Setup scrim highlights functionality
        setup_scrim_highlights(self)
        
        # Sync commands to the guild
        try:
            guild = discord.Object(id=self.guild_id)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} command(s) to guild {self.guild_id}")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when the bot is ready"""
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guild(s)')
        
        # Send the UI to the designated channel
        await self.send_ui_to_channel()
    
    async def send_ui_to_channel(self):
        """Send the minimalistic UI to the designated channel"""
        try:
            channel = self.get_channel(self.channel_id)
            if not channel:
                print(f"Channel with ID {self.channel_id} not found!")
                return
            
            # Purge all bot messages in the channel
            print("Purging old bot messages...")
            try:
                def is_bot_message(message):
                    return message.author == self.user
                
                deleted = await channel.purge(limit=100, check=is_bot_message)
                print(f"Deleted {len(deleted)} old bot messages")
            except Exception as e:
                print(f"Could not purge messages: {e}")
            
            # Create minimalistic embed
            embed = discord.Embed(
                title="Zero Remorse Scrim Highlights",
                description="Upload and share your best scrim moments with the team!",
                color=0x2F3136  # Dark gray color for minimalistic look
            )
            embed.set_footer(text="Zero Remorse Bot • Ready to capture your highlights")
            
            # Add the ZR.png image if it exists
            try:
                file = discord.File("GFX/ZR.png", filename="ZR.png")
                embed.set_thumbnail(url="attachment://ZR.png")
                
                await channel.send(
                    embed=embed,
                    view=UploadHighlightView(),
                    file=file
                )
            except FileNotFoundError:
                # Send without image if file doesn't exist
                await channel.send(
                    embed=embed,
                    view=UploadHighlightView()
                )
            
            print(f"UI sent to channel: #{channel.name}")
            
        except Exception as e:
            print(f"Error sending UI to channel: {e}")

# Create bot instance
bot = ZeroRemorseBot()

@bot.tree.command(name="setup_ui", description="Manually setup the scrim highlights UI", guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def setup_ui(interaction: discord.Interaction):
    """Slash command to manually setup the UI"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return
    
    await bot.send_ui_to_channel()
    await interaction.response.send_message("UI has been set up in the designated channel!", ephemeral=True)

if __name__ == "__main__":
    # Check if required environment variables are set
    required_vars = ['DISCORD_TOKEN', 'GUILD_ID', 'CHANNEL_ID', 'VALOM_ROLE_ID', 'GEMINI_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var) or os.getenv(var).startswith('your_')]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file and make sure all required variables are set.")
        exit(1)
    
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    except discord.LoginFailure:
        print("Invalid Discord token! Please check your DISCORD_TOKEN in the .env file.")
    except Exception as e:
        print(f"An error occurred: {e}")