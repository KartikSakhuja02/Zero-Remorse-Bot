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

@bot.tree.command(name="reset_stats", description="Reset all wins, losses, and draws count (Admin only)", guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def reset_stats(interaction: discord.Interaction):
    """Slash command to reset all match statistics"""
    if not interaction.user.guild_permissions.administrator:
        try:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        except discord.NotFound:
            print("Admin check interaction expired")
        return
    
    try:
        # Defer the response to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        # Import required modules
        import json
        import os
        from datetime import datetime
        
        json_file = "scrim_highlight.json"
        
        # Check if file exists and get current stats
        current_stats = {"wins": 0, "losses": 0, "draws": 0, "total_matches": 0}
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        # Count current stats
                        for entry in data.values():
                            if isinstance(entry, dict):
                                result = entry.get("result", "").lower()
                                if result == "win":
                                    current_stats["wins"] += 1
                                elif result == "defeat":
                                    current_stats["losses"] += 1
                                elif result == "draw":
                                    current_stats["draws"] += 1
                                current_stats["total_matches"] += 1
            except (FileNotFoundError, json.JSONDecodeError):
                pass  # File doesn't exist or is empty, stats remain 0
        
        # Create backup with timestamp
        backup_file = f"scrim_highlight_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        if os.path.exists(json_file):
            import shutil
            shutil.copy2(json_file, backup_file)
            print(f"Created backup: {backup_file}")
        
        # Clear the JSON file (reset to empty)
        with open(json_file, 'w') as f:
            json.dump({}, f, indent=2)
        
        # Send confirmation message
        embed = discord.Embed(
            title="📊 Statistics Reset Complete",
            description="All match statistics have been successfully reset to zero.",
            color=0xff6b6b
        )
        
        embed.add_field(
            name="Previous Stats",
            value=f"**Wins:** {current_stats['wins']}\n**Losses:** {current_stats['losses']}\n**Draws:** {current_stats['draws']}\n**Total Matches:** {current_stats['total_matches']}",
            inline=True
        )
        
        embed.add_field(
            name="Current Stats",
            value="**Wins:** 0\n**Losses:** 0\n**Draws:** 0\n**Total Matches:** 0",
            inline=True
        )
        
        embed.add_field(
            name="Backup Created",
            value=f"📁 `{backup_file}`",
            inline=False
        )
        
        embed.set_footer(text=f"Reset by {interaction.user.display_name} • Zero Remorse Stats")
        embed.timestamp = datetime.now()
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Stats reset by {interaction.user.display_name} ({interaction.user.id})")
        
    except discord.NotFound:
        print("Reset stats interaction expired")
    except Exception as e:
        print(f"Error resetting stats: {e}")
        try:
            await interaction.followup.send("❌ **Error**\n\nFailed to reset statistics. Please try again or contact support.", ephemeral=True)
        except:
            pass

@bot.tree.command(name="set_stats", description="Set specific wins, losses, and draws count (Admin only)", guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def set_stats(interaction: discord.Interaction, wins: int = 0, losses: int = 0, draws: int = 0):
    """Slash command to set specific match statistics"""
    if not interaction.user.guild_permissions.administrator:
        try:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        except discord.NotFound:
            print("Admin check interaction expired")
        return
    
    # Validate input
    if wins < 0 or losses < 0 or draws < 0:
        try:
            await interaction.response.send_message("❌ **Invalid Input**\n\nWins, losses, and draws must be non-negative numbers.", ephemeral=True)
        except discord.NotFound:
            print("Validation error interaction expired")
        return
        
    if wins > 9999 or losses > 9999 or draws > 9999:
        try:
            await interaction.response.send_message("❌ **Invalid Input**\n\nNumbers must be less than 10,000.", ephemeral=True)
        except discord.NotFound:
            print("Validation error interaction expired")
        return
    
    try:
        # Defer the response to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        # Import required modules
        import json
        import os
        from datetime import datetime
        
        json_file = "scrim_highlight.json"
        
        # Get current stats before modification
        current_stats = {"wins": 0, "losses": 0, "draws": 0, "total_matches": 0}
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        # Count current stats
                        for entry in data.values():
                            if isinstance(entry, dict):
                                result = entry.get("result", "").lower()
                                if result == "win":
                                    current_stats["wins"] += 1
                                elif result == "defeat":
                                    current_stats["losses"] += 1
                                elif result == "draw":
                                    current_stats["draws"] += 1
                                current_stats["total_matches"] += 1
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        
        # Create backup if file exists and has data
        if os.path.exists(json_file) and current_stats["total_matches"] > 0:
            backup_file = f"scrim_highlight_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import shutil
            shutil.copy2(json_file, backup_file)
            print(f"Created backup before stat modification: {backup_file}")
        
        # Create synthetic entries to match the desired stats
        new_data = {}
        entry_id = 1
        
        # Add wins
        for i in range(wins):
            entry = {
                "id": str(entry_id),
                "user_id": "admin_generated",
                "username": "Admin Set",
                "match_format": "BO1",
                "upload_type": "scrim",
                "clan_name": f"Synthetic Win {i+1}",
                "our_score": 13,
                "enemy_score": 10,
                "result": "win",
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "Admin Generated"
            }
            new_data[str(entry_id)] = entry
            entry_id += 1
        
        # Add losses
        for i in range(losses):
            entry = {
                "id": str(entry_id),
                "user_id": "admin_generated", 
                "username": "Admin Set",
                "match_format": "BO1",
                "upload_type": "scrim",
                "clan_name": f"Synthetic Loss {i+1}",
                "our_score": 10,
                "enemy_score": 13,
                "result": "defeat",
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "Admin Generated"
            }
            new_data[str(entry_id)] = entry
            entry_id += 1
        
        # Add draws
        for i in range(draws):
            entry = {
                "id": str(entry_id),
                "user_id": "admin_generated",
                "username": "Admin Set", 
                "match_format": "BO1",
                "upload_type": "scrim",
                "clan_name": f"Synthetic Draw {i+1}",
                "our_score": 12,
                "enemy_score": 12,
                "result": "draw",
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "Admin Generated"
            }
            new_data[str(entry_id)] = entry
            entry_id += 1
        
        # Save the new data
        with open(json_file, 'w') as f:
            json.dump(new_data, f, indent=2)
        
        # Send confirmation message
        total_new = wins + losses + draws
        embed = discord.Embed(
            title="📊 Statistics Updated",
            description=f"Match statistics have been set to the specified values.",
            color=0x00ff88
        )
        
        embed.add_field(
            name="Previous Stats",
            value=f"**Wins:** {current_stats['wins']}\n**Losses:** {current_stats['losses']}\n**Draws:** {current_stats['draws']}\n**Total:** {current_stats['total_matches']}",
            inline=True
        )
        
        embed.add_field(
            name="New Stats",
            value=f"**Wins:** {wins}\n**Losses:** {losses}\n**Draws:** {draws}\n**Total:** {total_new}",
            inline=True
        )
        
        if total_new > 0:
            embed.add_field(
                name="📝 Note",
                value="Synthetic match entries were created to achieve these statistics.",
                inline=False
            )
        
        embed.set_footer(text=f"Updated by {interaction.user.display_name} • Zero Remorse Stats")
        embed.timestamp = datetime.now()
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Stats set to W:{wins} L:{losses} D:{draws} by {interaction.user.display_name} ({interaction.user.id})")
        
    except discord.NotFound:
        print("Set stats interaction expired")
    except Exception as e:
        print(f"Error setting stats: {e}")
        try:
            await interaction.followup.send("❌ **Error**\n\nFailed to update statistics. Please try again or contact support.", ephemeral=True)
        except:
            pass

@bot.tree.context_menu(name="Edit Match Score", guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def edit_match_score_context(interaction: discord.Interaction, message: discord.Message):
    """Context menu command to edit match scores"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return
    
    # Verify it's a bot message with match results
    if message.author.id != bot.user.id or not message.embeds:
        await interaction.response.send_message("❌ This message doesn't contain match results to edit.", ephemeral=True)
        return
    
    # Check if it's a match result message
    embed = message.embeds[0]
    has_match_data = any(field.name in ["Match Result", "📊 Match Summary", "Score"] for field in embed.fields)
    
    if not has_match_data:
        await interaction.response.send_message("❌ This message doesn't contain match results to edit.", ephemeral=True)
        return
    
    # Create a modal for score editing
    modal = ScoreEditMatchModal(message)
    await interaction.response.send_modal(modal)

class ScoreEditMatchModal(discord.ui.Modal, title="Edit Match Score"):
    def __init__(self, message_to_edit):
        super().__init__()
        self.message_to_edit = message_to_edit
        
        # Try to extract current scores from the message
        current_our_score = 0
        current_enemy_score = 0
        
        if message_to_edit.embeds:
            embed = message_to_edit.embeds[0]
            for field in embed.fields:
                field_text = field.value.lower()
                if "our score:" in field_text:
                    try:
                        import re
                        match = re.search(r'our score:\*\*\s*(\d+)', field_text)
                        if match:
                            current_our_score = int(match.group(1))
                    except:
                        pass
                if "enemy score:" in field_text:
                    try:
                        import re
                        match = re.search(r'enemy score:\*\*\s*(\d+)', field_text)
                        if match:
                            current_enemy_score = int(match.group(1))
                    except:
                        pass
        
        # Set default values
        self.our_score.default = str(current_our_score) if current_our_score > 0 else ""
        self.enemy_score.default = str(current_enemy_score) if current_enemy_score > 0 else ""

    our_score = discord.ui.TextInput(
        label="Our Score",
        placeholder="Enter our team's score...",
        required=True,
        max_length=2
    )
    
    enemy_score = discord.ui.TextInput(
        label="Enemy Score", 
        placeholder="Enter enemy team's score...",
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_our_score = int(self.our_score.value)
            new_enemy_score = int(self.enemy_score.value)
            
            if new_our_score < 0 or new_enemy_score < 0:
                await interaction.response.send_message("❌ Scores cannot be negative!", ephemeral=True)
                return
                
            if new_our_score > 30 or new_enemy_score > 30:
                await interaction.response.send_message("❌ Scores seem too high! Please check your input.", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # Get the embed to edit
            embed = self.message_to_edit.embeds[0]
            
            # Determine the result based on scores
            if new_our_score > new_enemy_score:
                result = "WIN"
                result_emoji = "🏆"
                color = 0x00ff88
            elif new_our_score < new_enemy_score:
                result = "DEFEAT"
                result_emoji = "💔"
                color = 0xff4444
            else:
                result = "DRAW"
                result_emoji = "🤝"
                color = 0xffaa00
            
            # Update embed title if it exists
            if embed.title:
                # Update title with new result
                if "WIN" in embed.title or "DEFEAT" in embed.title or "DRAW" in embed.title:
                    parts = embed.title.split(" ")
                    # Replace the result part
                    for i, part in enumerate(parts):
                        if part in ["WIN", "DEFEAT", "DRAW"]:
                            parts[i] = result
                            break
                    embed.title = " ".join(parts)
            
            # Update embed color
            embed.color = color
            
            # Update fields with new scores
            for field in embed.fields:
                if "Score" in field.name or "Result" in field.name or "Match Summary" in field.name:
                    # Update the score in the field value
                    field_lines = field.value.split('\n')
                    updated_lines = []
                    
                    for line in field_lines:
                        if "**Our Score:**" in line:
                            updated_lines.append(f"**Our Score:** {new_our_score}")
                        elif "**Enemy Score:**" in line:
                            updated_lines.append(f"**Enemy Score:** {new_enemy_score}")
                        elif "**Result:**" in line:
                            updated_lines.append(f"**Result:** {result_emoji} {result}")
                        elif "**Final Score:**" in line:
                            updated_lines.append(f"**Final Score:** {new_our_score} - {new_enemy_score}")
                        else:
                            updated_lines.append(line)
                    
                    field.value = '\n'.join(updated_lines)
            
            # Update the message
            await self.message_to_edit.edit(embed=embed)
            
            # Also update the JSON data
            try:
                import json
                from datetime import datetime, timedelta
                
                json_file = "scrim_highlight.json"
                
                if os.path.exists(json_file):
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    
                    # Find and update the corresponding entry
                    message_time = self.message_to_edit.created_at
                    
                    for entry_id, entry in data.items():
                        if isinstance(entry, dict):
                            try:
                                entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
                                time_diff = abs((message_time.replace(tzinfo=None) - entry_time).total_seconds())
                                
                                if time_diff < 300:  # Within 5 minutes
                                    # Update the entry
                                    entry["our_score"] = new_our_score
                                    entry["enemy_score"] = new_enemy_score
                                    
                                    # Update result
                                    if new_our_score > new_enemy_score:
                                        entry["result"] = "win"
                                    elif new_our_score < new_enemy_score:
                                        entry["result"] = "defeat"
                                    else:
                                        entry["result"] = "draw"
                                    
                                    entry["edited"] = True
                                    entry["edited_by"] = interaction.user.display_name
                                    entry["edited_at"] = datetime.now().isoformat()
                                    
                                    # Save updated data
                                    with open(json_file, 'w') as f:
                                        json.dump(data, f, indent=2)
                                    
                                    break
                            except:
                                continue
            except Exception as e:
                print(f"Error updating JSON data: {e}")
            
            # Send confirmation
            embed_confirm = discord.Embed(
                title="✅ Match Score Updated",
                description=f"Successfully updated the match result.",
                color=0x00ff88
            )
            
            embed_confirm.add_field(
                name="Updated Scores",
                value=f"**Our Score:** {new_our_score}\n**Enemy Score:** {new_enemy_score}\n**Result:** {result_emoji} {result}",
                inline=False
            )
            
            embed_confirm.set_footer(text=f"Edited by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed_confirm, ephemeral=True)
            print(f"Match score edited by {interaction.user.display_name}: {new_our_score}-{new_enemy_score}")
            
        except ValueError:
            await interaction.response.send_message("❌ Please enter valid numbers for the scores!", ephemeral=True)
        except Exception as e:
            print(f"Error in score edit modal: {e}")
            try:
                await interaction.followup.send("❌ Failed to update the match score. Please try again.", ephemeral=True)
            except:
                pass

@bot.tree.command(name="edit_message", description="Edit a bot message by replying to it (Admin only)", guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def edit_message(interaction: discord.Interaction, new_our_score: int, new_enemy_score: int):
    """Slash command to edit a bot message's score by replying to it"""
    if not interaction.user.guild_permissions.administrator:
        try:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        except discord.NotFound:
            print("Admin check interaction expired")
        return
    
    try:
        # Check if this is a reply to a message
        if not hasattr(interaction, 'message') or not interaction.message:
            # Check if there's a referenced message in the channel
            referenced_message = None
            
            # Try to get the message being replied to from recent messages
            async for message in interaction.channel.history(limit=10):
                if message.author.id == bot.user.id and message.embeds:
                    # Check if this looks like a match result message
                    embed = message.embeds[0]
                    if any(field.name in ["Match Result", "📊 Match Summary"] for field in embed.fields):
                        referenced_message = message
                        break
            
            if not referenced_message:
                await interaction.response.send_message(
                    "❌ **Error**\n\nPlease reply to a bot message containing match results to edit it.", 
                    ephemeral=True
                )
                return
        else:
            referenced_message = interaction.message
        
        # Verify it's a bot message with embeds
        if referenced_message.author.id != bot.user.id:
            await interaction.response.send_message(
                "❌ **Error**\n\nYou can only edit messages sent by the bot.", 
                ephemeral=True
            )
            return
        
        if not referenced_message.embeds:
            await interaction.response.send_message(
                "❌ **Error**\n\nThis message doesn't contain match results to edit.", 
                ephemeral=True
            )
            return
        
        # Defer the response
        await interaction.response.defer(ephemeral=True)
        
        # Get the embed to edit
        embed = referenced_message.embeds[0]
        
        # Determine the result based on scores
        if new_our_score > new_enemy_score:
            result = "WIN"
            result_emoji = "🏆"
            color = 0x00ff88
        elif new_our_score < new_enemy_score:
            result = "DEFEAT"
            result_emoji = "💔"
            color = 0xff4444
        else:
            result = "DRAW"
            result_emoji = "🤝"
            color = 0xffaa00
        
        # Update embed title if it exists
        if embed.title:
            # Update title with new result
            if "WIN" in embed.title or "DEFEAT" in embed.title or "DRAW" in embed.title:
                parts = embed.title.split(" ")
                # Replace the result part
                for i, part in enumerate(parts):
                    if part in ["WIN", "DEFEAT", "DRAW"]:
                        parts[i] = result
                        break
                embed.title = " ".join(parts)
        
        # Update embed color
        embed.color = color
        
        # Update fields with new scores
        for field in embed.fields:
            if "Score" in field.name or "Result" in field.name or "Match Summary" in field.name:
                # Update the score in the field value
                field_lines = field.value.split('\n')
                updated_lines = []
                
                for line in field_lines:
                    if "**Our Score:**" in line:
                        updated_lines.append(f"**Our Score:** {new_our_score}")
                    elif "**Enemy Score:**" in line:
                        updated_lines.append(f"**Enemy Score:** {new_enemy_score}")
                    elif "**Result:**" in line:
                        updated_lines.append(f"**Result:** {result_emoji} {result}")
                    elif "**Final Score:**" in line:
                        updated_lines.append(f"**Final Score:** {new_our_score} - {new_enemy_score}")
                    else:
                        updated_lines.append(line)
                
                field.value = '\n'.join(updated_lines)
        
        # Update the message
        await referenced_message.edit(embed=embed)
        
        # Also update the JSON data if this was from a match upload
        try:
            import json
            json_file = "scrim_highlight.json"
            
            if os.path.exists(json_file):
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                # Find and update the corresponding entry
                # Look for entries with timestamps close to the message creation time
                message_time = referenced_message.created_at
                
                for entry_id, entry in data.items():
                    if isinstance(entry, dict):
                        # Check if this entry matches the message timing (within 5 minutes)
                        try:
                            from datetime import datetime, timedelta
                            entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
                            time_diff = abs((message_time.replace(tzinfo=None) - entry_time).total_seconds())
                            
                            if time_diff < 300:  # Within 5 minutes
                                # Update the entry
                                entry["our_score"] = new_our_score
                                entry["enemy_score"] = new_enemy_score
                                
                                # Update result
                                if new_our_score > new_enemy_score:
                                    entry["result"] = "win"
                                elif new_our_score < new_enemy_score:
                                    entry["result"] = "defeat"
                                else:
                                    entry["result"] = "draw"
                                
                                entry["edited"] = True
                                entry["edited_by"] = interaction.user.display_name
                                entry["edited_at"] = datetime.now().isoformat()
                                
                                # Save updated data
                                with open(json_file, 'w') as f:
                                    json.dump(data, f, indent=2)
                                
                                break
                        except:
                            continue
        except Exception as e:
            print(f"Error updating JSON data: {e}")
        
        # Send confirmation
        embed_confirm = discord.Embed(
            title="✅ Message Edited Successfully",
            description=f"Updated the match result with new scores.",
            color=0x00ff88
        )
        
        embed_confirm.add_field(
            name="Updated Scores",
            value=f"**Our Score:** {new_our_score}\n**Enemy Score:** {new_enemy_score}\n**Result:** {result_emoji} {result}",
            inline=False
        )
        
        embed_confirm.set_footer(text=f"Edited by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed_confirm, ephemeral=True)
        print(f"Message edited by {interaction.user.display_name}: {new_our_score}-{new_enemy_score}")
        
    except discord.NotFound:
        print("Edit message interaction expired")
    except Exception as e:
        print(f"Error editing message: {e}")
        try:
            await interaction.followup.send("❌ **Error**\n\nFailed to edit the message. Please try again.", ephemeral=True)
        except:
            pass

@bot.tree.command(name="edit_stats", description="Edit current win/loss/draw counts (Admin only)", guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def edit_stats(interaction: discord.Interaction, wins_change: int = 0, losses_change: int = 0, draws_change: int = 0):
    """Slash command to modify current match statistics by adding/subtracting"""
    if not interaction.user.guild_permissions.administrator:
        try:
            await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        except discord.NotFound:
            print("Admin check interaction expired")
        return
    
    try:
        # Defer the response to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        # Import required modules
        import json
        import os
        from datetime import datetime
        
        json_file = "scrim_highlight.json"
        
        # Get current stats
        current_stats = {"wins": 0, "losses": 0, "draws": 0, "total_matches": 0}
        existing_data = {}
        
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        existing_data = json.loads(content)
                        # Count current stats
                        for entry in existing_data.values():
                            if isinstance(entry, dict):
                                result = entry.get("result", "").lower()
                                if result == "win":
                                    current_stats["wins"] += 1
                                elif result == "defeat":
                                    current_stats["losses"] += 1
                                elif result == "draw":
                                    current_stats["draws"] += 1
                                current_stats["total_matches"] += 1
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        
        # Calculate new stats
        new_wins = max(0, current_stats["wins"] + wins_change)
        new_losses = max(0, current_stats["losses"] + losses_change)
        new_draws = max(0, current_stats["draws"] + draws_change)
        
        # Check if no changes needed
        if wins_change == 0 and losses_change == 0 and draws_change == 0:
            embed = discord.Embed(
                title="📊 Current Statistics",
                description="No changes were made. Here are your current stats:",
                color=0x3498db
            )
            embed.add_field(
                name="Current Stats",
                value=f"**Wins:** {current_stats['wins']}\n**Losses:** {current_stats['losses']}\n**Draws:** {current_stats['draws']}\n**Total:** {current_stats['total_matches']}",
                inline=False
            )
            embed.set_footer(text=f"Use /edit_stats wins_change:5 to add 5 wins, or wins_change:-2 to subtract 2 wins")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Create backup if there's existing data
        if current_stats["total_matches"] > 0:
            backup_file = f"scrim_highlight_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import shutil
            shutil.copy2(json_file, backup_file)
            print(f"Created backup before stat edit: {backup_file}")
        
        # Get the highest existing ID
        max_id = 0
        for existing_id in existing_data.keys():
            try:
                id_num = int(existing_id)
                max_id = max(max_id, id_num)
            except ValueError:
                continue
        
        # Keep existing data and add/remove synthetic entries as needed
        new_data = existing_data.copy()
        entry_id = max_id + 1
        
        # Calculate how many entries to add/remove for each type
        wins_to_add = new_wins - current_stats["wins"]
        losses_to_add = new_losses - current_stats["losses"] 
        draws_to_add = new_draws - current_stats["draws"]
        
        # Add wins if needed
        for i in range(wins_to_add):
            entry = {
                "id": str(entry_id),
                "user_id": "admin_edited",
                "username": "Stats Edit",
                "match_format": "BO1",
                "upload_type": "scrim",
                "clan_name": f"Added Win {i+1}",
                "our_score": 13,
                "enemy_score": 10,
                "result": "win",
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "Admin Edit"
            }
            new_data[str(entry_id)] = entry
            entry_id += 1
        
        # Add losses if needed
        for i in range(losses_to_add):
            entry = {
                "id": str(entry_id),
                "user_id": "admin_edited",
                "username": "Stats Edit",
                "match_format": "BO1", 
                "upload_type": "scrim",
                "clan_name": f"Added Loss {i+1}",
                "our_score": 10,
                "enemy_score": 13,
                "result": "defeat",
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "Admin Edit"
            }
            new_data[str(entry_id)] = entry
            entry_id += 1
        
        # Add draws if needed
        for i in range(draws_to_add):
            entry = {
                "id": str(entry_id),
                "user_id": "admin_edited",
                "username": "Stats Edit",
                "match_format": "BO1",
                "upload_type": "scrim", 
                "clan_name": f"Added Draw {i+1}",
                "our_score": 12,
                "enemy_score": 12,
                "result": "draw",
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "Admin Edit"
            }
            new_data[str(entry_id)] = entry
            entry_id += 1
        
        # Remove entries if needed (remove synthetic entries first, then oldest)
        if wins_to_add < 0:  # Need to remove wins
            wins_to_remove = abs(wins_to_add)
            removed = 0
            for entry_id in list(new_data.keys()):
                if removed >= wins_to_remove:
                    break
                entry = new_data[entry_id]
                if isinstance(entry, dict) and entry.get("result") == "win":
                    del new_data[entry_id]
                    removed += 1
        
        if losses_to_add < 0:  # Need to remove losses
            losses_to_remove = abs(losses_to_add)
            removed = 0
            for entry_id in list(new_data.keys()):
                if removed >= losses_to_remove:
                    break
                entry = new_data[entry_id]
                if isinstance(entry, dict) and entry.get("result") == "defeat":
                    del new_data[entry_id]
                    removed += 1
        
        if draws_to_add < 0:  # Need to remove draws
            draws_to_remove = abs(draws_to_add)
            removed = 0
            for entry_id in list(new_data.keys()):
                if removed >= draws_to_remove:
                    break
                entry = new_data[entry_id]
                if isinstance(entry, dict) and entry.get("result") == "draw":
                    del new_data[entry_id]
                    removed += 1
        
        # Save the updated data
        with open(json_file, 'w') as f:
            json.dump(new_data, f, indent=2)
        
        # Send confirmation message
        total_new = new_wins + new_losses + new_draws
        embed = discord.Embed(
            title="📊 Statistics Edited",
            description=f"Match statistics have been updated with your changes.",
            color=0x00ff88
        )
        
        embed.add_field(
            name="Previous Stats",
            value=f"**Wins:** {current_stats['wins']}\n**Losses:** {current_stats['losses']}\n**Draws:** {current_stats['draws']}\n**Total:** {current_stats['total_matches']}",
            inline=True
        )
        
        embed.add_field(
            name="Changes Applied",
            value=f"**Wins:** {wins_change:+}\n**Losses:** {losses_change:+}\n**Draws:** {draws_change:+}",
            inline=True
        )
        
        embed.add_field(
            name="New Stats",
            value=f"**Wins:** {new_wins}\n**Losses:** {new_losses}\n**Draws:** {new_draws}\n**Total:** {total_new}",
            inline=True
        )
        
        embed.set_footer(text=f"Edited by {interaction.user.display_name} • Zero Remorse Stats")
        embed.timestamp = datetime.now()
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Stats edited by {interaction.user.display_name}: W{wins_change:+} L{losses_change:+} D{draws_change:+}")
        
    except discord.NotFound:
        print("Edit stats interaction expired")
    except Exception as e:
        print(f"Error editing stats: {e}")
        try:
            await interaction.followup.send("❌ **Error**\n\nFailed to edit statistics. Please try again or contact support.", ephemeral=True)
        except:
            pass

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