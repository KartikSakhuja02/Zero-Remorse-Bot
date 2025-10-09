import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import logging
from scrim_highlights import ScrimHighlightModal, setup_scrim_highlights

# Try to import keep_alive for hosting platforms that need it
try:
    from keep_alive import keep_alive
    KEEP_ALIVE_AVAILABLE = True
except ImportError:
    KEEP_ALIVE_AVAILABLE = False
    print("ℹ️  Keep-alive not available (Flask not installed)")
    # Force deployment refresh

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)

# Verify required environment variables
required_vars = [
    'DISCORD_TOKEN', 
    'GUILD_ID', 
    'CHANNEL_ID', 
    'VALOM_ROLE_ID', 
    'SCRIM_HIGHLIGHTS_CHANNEL_ID',
    'TOURNAMENT_HIGHLIGHTS_CHANNEL_ID',
    'GEMINI_API_KEY'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
    print("Please set these variables in your hosting platform's environment settings.")
    exit(1)

print("✅ All required environment variables found!")

class UploadTypeView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
    
    @discord.ui.select(
        placeholder="Choose upload type...",
        options=[
            discord.SelectOption(label="Scrim", description="Upload scrim match highlights", emoji="⚔️", value="scrim"),
            discord.SelectOption(label="Tournament", description="Upload tournament match highlights", emoji="🏆", value="tournament"),
        ]
    )
    async def select_upload_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_type = select.values[0]
        
        # Store the selected upload type for this user
        if not hasattr(interaction.client, 'user_upload_types'):
            interaction.client.user_upload_types = {}
        interaction.client.user_upload_types[self.user_id] = selected_type
        
        # Create appropriate embed title and description based on type
        if selected_type == "scrim":
            title = "Scrim Highlight Upload"
            description_type = "scrim match"
            color = 0x9d4edd  # Purple for scrims
        else:  # tournament
            title = "Tournament Highlight Upload"
            description_type = "tournament match"
            color = 0xffd700  # Gold for tournaments
        
        # Ask for match format
        format_embed = discord.Embed(
            title=title,
            description=f"**Step 2: Select Match Format**\n\n"
                       f"Please select what type of {description_type} this highlight is from using the dropdown below.",
            color=color
        )
        format_embed.set_footer(text=f"Zero Remorse • {selected_type.title()} Highlights System")
        
        # Create the match format view
        view = MatchFormatView(self.user_id)
        try:
            await interaction.response.edit_message(embed=format_embed, view=view)
        except discord.NotFound:
            # Interaction expired
            print(f"Interaction expired while editing message for upload type selection")
        except Exception as e:
            print(f"Error editing message for upload type: {e}")

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
        
        # Get upload type to customize the title
        upload_type = getattr(interaction.client, 'user_upload_types', {}).get(self.user_id, 'scrim')
        title_prefix = "Tournament" if upload_type == "tournament" else "Scrim"
        color = 0xffd700 if upload_type == "tournament" else 0xffa500
        
        # Ask for clan name
        clan_embed = discord.Embed(
            title=f"Enter {title_prefix} Opponent Name",
            description=f"**Step 3: Enter Opponent Name**\n\n"
                       f"Upload Type: **{title_prefix}**\n"
                       f"Match Format: **{selected_format}** (Best of {selected_format[2]})\n\n"
                       f"**Please type the name of the team/clan you played against:**\n"
                       f"Just send a message with the opponent name.\n"
                       f"Type **'cancel'** to abort this process.\n\n"
                       f"**Example:**\n"
                       f"*Team Liquid*",
            color=color
        )
        clan_embed.set_footer(text=f"Zero Remorse • Waiting for opponent name...")
        
        try:
            await interaction.response.edit_message(embed=clan_embed, view=None)
        except discord.NotFound:
            # Interaction expired
            print(f"Interaction expired while editing message for match format selection")
        except Exception as e:
            print(f"Error editing message for match format: {e}")

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
        # Try to defer the response immediately to prevent timeout issues
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            # Interaction has expired, just return silently
            print(f"Interaction expired for user {interaction.user.display_name}")
            return
        except Exception as e:
            print(f"Error deferring interaction: {e}")
            return
        
        # Check if user has the Valom role using role ID
        valom_role_id = int(os.getenv('VALOM_ROLE_ID'))
        has_valom_role = any(role.id == valom_role_id for role in interaction.user.roles)
        
        if not has_valom_role:
            # User doesn't have Valom role
            await interaction.followup.send(
                "**Access Denied**\n\nYou don't have the required **Valom** role to upload scrim highlights.",
                ephemeral=True
            )
            return
        
        # User has Valom role - send DM with upload type selection
        try:
            dm_embed = discord.Embed(
                title="Highlight Upload",
                description="**Step 1: Select Upload Type**\n\n"
                           "Please select what type of highlight you want to upload using the dropdown below.",
                color=0x9d4edd
            )
            dm_embed.set_footer(text="Zero Remorse • Highlight Upload System")
            
            # Create the view with upload type dropdown
            view = UploadTypeView(interaction.user.id)
            await interaction.user.send(embed=dm_embed, view=view)
            
            # Confirm in the channel (ephemeral) using followup
            await interaction.followup.send(
                "**Check your DMs!**\n\n"
                "I've sent you instructions for uploading your scrim highlight. "
                "Please send your screenshot/video in our DM conversation.",
                ephemeral=True
            )
            
        except discord.Forbidden:
            # User has DMs disabled
            await interaction.followup.send(
                "**Cannot send DM**\n\n"
                "Please enable DMs from server members so I can send you upload instructions.\n"
                "Go to: **Server Settings → Privacy Settings → Allow direct messages from server members**",
                ephemeral=True
            )
        except Exception as e:
            # Handle any other errors
            print(f"Error in upload_highlight: {e}")
            await interaction.followup.send(
                "**Error**\n\nSomething went wrong while setting up your highlight upload. Please try again.",
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
        
        # Will be created in setup_hook when event loop is available
        self.upload_view = None
    
    async def setup_hook(self):
        """This is called when the bot starts up"""
        # Create the single persistent view instance (now that event loop is running)
        self.upload_view = UploadHighlightView()
        self.add_view(self.upload_view)
        
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
    
    async def send_ui_to_channel(self, force_recreate=False):
        """Send the minimalistic UI to the designated channel"""
        try:
            channel = self.get_channel(self.channel_id)
            if not channel:
                print(f"Channel with ID {self.channel_id} not found!")
                return
            
            # Check if UI already exists (unless force recreate is requested)
            if not force_recreate:
                print("Checking for existing UI...")
                async for message in channel.history(limit=50):
                    if (message.author == self.user and 
                        message.embeds and 
                        "Zero Remorse Scrim Highlights" in message.embeds[0].title and
                        message.components):  # Has buttons/view components
                        print("Existing UI found, skipping creation")
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
                    view=self.upload_view,
                    file=file
                )
            except FileNotFoundError:
                # Send without image if file doesn't exist
                await channel.send(
                    embed=embed,
                    view=self.upload_view
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
        try:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        except discord.NotFound:
            print("Admin check interaction expired")
        return
    
    await bot.send_ui_to_channel(force_recreate=True)
    try:
        await interaction.response.send_message("UI has been recreated in the designated channel!", ephemeral=True)
    except discord.NotFound:
        print("Setup UI success interaction expired")
    except Exception as e:
        print(f"Error responding to setup UI command: {e}")

if __name__ == "__main__":
    # Get port for web services (required by some hosting platforms)
    port = int(os.environ.get('PORT', 8080))
    
    print(f"🚀 Starting Zero Remorse Discord Bot...")
    print(f"📋 Required environment variables verified")
    print(f"🌐 Port configured: {port}")
    
    # Start keep-alive web server if available (for hosting platforms)
    if KEEP_ALIVE_AVAILABLE:
        keep_alive()
        print("🔄 Keep-alive server started")
    
    try:
        # Run the bot
        bot.run(os.getenv('DISCORD_TOKEN'))
    except discord.LoginFailure:
        print("❌ Invalid Discord token! Please check your DISCORD_TOKEN environment variable.")
    except discord.HTTPException as e:
        print(f"❌ Discord HTTP error: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()