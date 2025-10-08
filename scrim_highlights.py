import discord
from discord.ext import commands
import os
from datetime import datetime
import asyncio
import json
from scrim_highlight_ocr import ValOCRHandler

class ScrimHighlightModal(discord.ui.Modal, title='Upload Scrim Highlight'):
    def __init__(self):
        super().__init__(timeout=300)  # 5 minute timeout
    
    highlight_title = discord.ui.TextInput(
        label='Highlight Title',
        placeholder='Enter a title for your highlight...',
        max_length=100,
        required=True
    )
    
    description = discord.ui.TextInput(
        label='Description',
        style=discord.TextStyle.paragraph,
        placeholder='Describe what happened in this highlight...',
        max_length=500,
        required=False
    )
    
    map_name = discord.ui.TextInput(
        label='Map Name',
        placeholder='e.g., Ascent, Bind, Haven...',
        max_length=50,
        required=False
    )
    
    players_involved = discord.ui.TextInput(
        label='Players Involved',
        placeholder='Tag teammates involved in this play...',
        max_length=200,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        embed = discord.Embed(
            title="Highlight Details Submitted",
            description=f"**{self.highlight_title.value}**\n\n{self.description.value or 'No description provided.'}",
            color=0x00ff00,  # Green color
            timestamp=datetime.now()
        )
        
        if self.map_name.value:
            embed.add_field(name="Map", value=self.map_name.value, inline=True)
        
        if self.players_involved.value:
            embed.add_field(name="Players", value=self.players_involved.value, inline=True)
        
        embed.add_field(
            name="Next Step", 
            value="**Upload your video file in this channel!**\n"
                  "• Drag & drop or attach your highlight video\n"
                  "• Supported: .mp4, .mov, .avi, .gif, .mkv, .webm\n"
                  "• Max size: 50MB", 
            inline=False
        )
        embed.set_footer(text=f"Submitted by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Store the highlight info for when they upload the file
        # In a real bot, you'd want to use a database for this
        if not hasattr(interaction.client, 'pending_highlights'):
            interaction.client.pending_highlights = {}
        
        interaction.client.pending_highlights[interaction.user.id] = {
            'title': self.highlight_title.value,
            'description': self.description.value,
            'map_name': self.map_name.value,
            'players_involved': self.players_involved.value,
            'timestamp': datetime.now()
        }

class ScrimHighlightHandler:
    def __init__(self, bot):
        self.bot = bot
        self.json_file = "scrim_highlight.json"
    
    def load_highlights_data(self):
        """Load highlights data from JSON file"""
        try:
            with open(self.json_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_highlights_data(self, data):
        """Save highlights data to JSON file"""
        try:
            with open(self.json_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Saved highlight data to {self.json_file}")
        except Exception as e:
            print(f"Error saving highlights data: {e}")
    
    async def process_dm_highlight(self, message, bot):
        """Process highlight uploads from DMs"""
        print(f"DM received from {message.author.display_name}: {message.content[:50]}...")
        print(f"Has attachments: {len(message.attachments) > 0}")
        
        # Check if user has Valom role in the guild
        guild = bot.get_guild(int(os.getenv('GUILD_ID')))
        if not guild:
            await message.reply("Could not find the server. Please try again later.")
            return
        
        # Try to get member, if not found try to fetch from API
        member = guild.get_member(message.author.id)
        if not member:
            try:
                member = await guild.fetch_member(message.author.id)
            except discord.NotFound:
                await message.reply("You are not a member of the Zero Remorse server.")
                return
            except Exception as e:
                print(f"Error fetching member: {e}")
                await message.reply("Could not verify your membership. Please try again later.")
                return
        
        valom_role_id = int(os.getenv('VALOM_ROLE_ID'))
        has_valom_role = any(role.id == valom_role_id for role in member.roles)
        if not has_valom_role:
            await message.reply("You don't have the required **Valom** role to upload highlights.")
            return
        
        print("User passed all validation checks")
        
        # Check if user wants to cancel any ongoing process
        if message.content.strip().lower() == "cancel":
            await self.handle_cancel_request(message, bot)
            return
        
        # Check if user is sending a file (has attachments)
        if message.attachments:
            print("User sent file attachment")
            # Check if user has both format and clan name stored
            has_format = hasattr(bot, 'user_match_formats') and message.author.id in bot.user_match_formats
            has_clan = hasattr(bot, 'user_clan_names') and message.author.id in bot.user_clan_names
            
            print(f"Has format: {has_format}")
            print(f"Has clan: {has_clan}")
            
            if has_format and has_clan:
                print("Processing file upload...")
                await self.process_file_upload(message, bot)
                return
            else:
                print("Missing format or clan data")
                await message.reply("Please use the button in the server channel to start uploading a highlight!")
                return
        
        # Check if user typed "done" for multi-map processing
        if message.content.strip().lower() == "done":
            if hasattr(bot, 'user_multi_map_data') and message.author.id in bot.user_multi_map_data:
                print("Processing multi-map 'done' command...")
                await self.process_multi_map_screenshots(message, bot)
                return
        
        # Check if user has selected a match format but no clan name yet (text message, no file)
        has_format = hasattr(bot, 'user_match_formats') and message.author.id in bot.user_match_formats
        has_clan = hasattr(bot, 'user_clan_names') and message.author.id in bot.user_clan_names
        
        print(f"Text message - Has format: {has_format}, Has clan: {has_clan}")
        
        if has_format and not has_clan:
            print("Processing clan name input...")
            # This is a clan name input
            await self.process_clan_name_input(message, bot)
            return
        
        # If no attachments and no format selected, send instructions
        print("No valid state found, sending instructions")
        await message.reply("Please use the button in the server channel to start uploading a highlight!")
    
    async def handle_cancel_request(self, message, bot):
        """Handle user cancel request - clear all stored data for this user"""
        user_id = message.author.id
        cancelled_processes = []
        
        # Clear match format selection
        if hasattr(bot, 'user_match_formats') and user_id in bot.user_match_formats:
            del bot.user_match_formats[user_id]
            cancelled_processes.append("Match format selection")
        
        # Clear clan name input
        if hasattr(bot, 'user_clan_names') and user_id in bot.user_clan_names:
            del bot.user_clan_names[user_id]
            cancelled_processes.append("Clan name input")
        
        # Clear multi-map screenshot collection
        if hasattr(bot, 'user_multi_map_data') and user_id in bot.user_multi_map_data:
            format_type = bot.user_multi_map_data[user_id].get('match_format', 'Multi-map')
            screenshot_count = len(bot.user_multi_map_data[user_id].get('screenshots', []))
            del bot.user_multi_map_data[user_id]
            cancelled_processes.append(f"{format_type} screenshot collection ({screenshot_count} screenshots)")
        
        if cancelled_processes:
            process_list = ", ".join(cancelled_processes)
            embed = discord.Embed(
                title="❌ Process Cancelled",
                description=f"Successfully cancelled: {process_list}\n\nYou can start over by using the button in the server channel.",
                color=0xff4444
            )
            embed.set_footer(text="Zero Remorse • Process cancelled")
            await message.reply(embed=embed)
            print(f"Cancelled processes for {message.author.display_name}: {process_list}")
        else:
            embed = discord.Embed(
                title="ℹ️ No Active Process",
                description="You don't have any active highlight upload process to cancel.\n\nUse the button in the server channel to start uploading a highlight.",
                color=0x3498db
            )
            embed.set_footer(text="Zero Remorse • Nothing to cancel")
            await message.reply(embed=embed)
    
    async def process_clan_name_input(self, message, bot):
        """Process clan name input from user"""
        clan_name = message.content.strip()
        
        # Cancel is already handled in the main process_dm_highlight function
        # so this function will only receive non-cancel messages
        
        if not clan_name:
            await message.reply("Please provide a valid clan name or type **'cancel'** to abort!")
            return
        
        # Store clan name for this user
        if not hasattr(bot, 'user_clan_names'):
            bot.user_clan_names = {}
        bot.user_clan_names[message.author.id] = clan_name
        print(f"Stored clan name '{clan_name}' for user {message.author.display_name}")
        
        # Get the selected format
        selected_format = bot.user_match_formats.get(message.author.id, "Unknown")
        
        # Send file upload instructions based on format
        if selected_format in ["BO2", "BO3", "BO4", "BO5"]:
            format_num = int(selected_format[2])
            max_maps = (format_num + 1) // 2  # BO3=2, BO5=3, etc.
            
            upload_embed = discord.Embed(
                title="Scrim Highlight Upload",
                description=f"**Step 3: Upload Your Screenshots**\n\n"
                           f"Match Format: **{selected_format}** (Best of {format_num})\n"
                           f"Clan: **{clan_name}**\n\n"
                           f"**For {selected_format}, send up to {max_maps} screenshots:**\n"
                           f"• Send 1 screenshot for each map you WON\n"
                           f"• Example: If you won 2-1, send 2 screenshots\n"
                           f"• Example: If you won 3-0, send 1 screenshot\n\n"
                           f"**Send your screenshots now, then type 'done' when finished**\n"
                           f"**Type 'cancel' to abort this process**\n\n"
                           f"**Supported formats:** .png, .jpg, .jpeg\n"
                           f"**Max file size:** 50MB per image",
                color=0xffa500
            )
        else:
            upload_embed = discord.Embed(
                title="Scrim Highlight Upload",
                description=f"**Step 3: Upload Your Highlight**\n\n"
                           f"Match Format: **{selected_format}** (Best of {selected_format[2]})\n"
                           f"Clan: **{clan_name}**\n\n"
                           f"**Now send your highlight file:**\n"
                           f"• Attach your video/screenshot\n"
                           f"• Type 'cancel' to abort this process\n\n"
                           f"**Supported formats:** .mp4, .mov, .avi, .gif, .png, .jpg\n"
                           f"**Max file size:** 50MB",
            color=0x00ff00
        )
        upload_embed.set_footer(text="Zero Remorse • Ready for your highlight!")
        
        await message.reply(embed=upload_embed)
    
    async def process_file_upload(self, message, bot):
        """Process file upload from user"""
        print("=== STARTING FILE UPLOAD PROCESS ===")
        attachment = message.attachments[0]
        valid_extensions = ['.mp4', '.mov', '.avi', '.gif', '.mkv', '.webm', '.png', '.jpg', '.jpeg']
        
        if not any(attachment.filename.lower().endswith(ext) for ext in valid_extensions):
            await message.reply("Please upload a valid file (.mp4, .mov, .avi, .gif, .png, .jpg, etc.)")
            return
        
        # Check file size (50MB limit)
        if attachment.size > 50 * 1024 * 1024:  # 50MB in bytes
            await message.reply("File too large! Please keep files under 50MB.")
            return
        
        # Get the highlights channel
        highlights_channel = bot.get_channel(int(os.getenv('CHANNEL_ID')))
        if not highlights_channel:
            await message.reply("Could not find the highlights channel.")
            return
        
        # Get stored data
        selected_format = bot.user_match_formats.get(message.author.id, "Unknown")
        clan_name = bot.user_clan_names.get(message.author.id, "Unknown")
        
        # Debug prints
        print(f"Processing file upload for user {message.author.display_name}")
        print(f"Selected format: {selected_format}")
        print(f"Clan name: {clan_name}")
        print(f"Has format stored: {hasattr(bot, 'user_match_formats') and message.author.id in bot.user_match_formats}")
        print(f"Has clan stored: {hasattr(bot, 'user_clan_names') and message.author.id in bot.user_clan_names}")
        
        # Check if we have valid data
        if selected_format == "Unknown" or clan_name == "Unknown":
            await message.reply("Missing match format or clan name. Please restart the process using the button in the server channel.")
            return
        
        # Special handling for BO1 - use OCR to extract scores
        if selected_format == "BO1":
            print("BO1 detected - using OCR processing")
            ocr_handler = ValOCRHandler()
            
            # Store clan name in the OCR data
            if not hasattr(bot, 'user_ocr_data'):
                bot.user_ocr_data = {}
            bot.user_ocr_data[message.author.id] = {"clan_name": clan_name, "match_format": selected_format}
            
            await ocr_handler.process_valorant_screenshot(message, bot, selected_format)
            
            # Clean up stored data after OCR processing
            if hasattr(bot, 'user_match_formats') and message.author.id in bot.user_match_formats:
                del bot.user_match_formats[message.author.id]
            if hasattr(bot, 'user_clan_names') and message.author.id in bot.user_clan_names:
                del bot.user_clan_names[message.author.id]
            
            return
        
        # Special handling for BO2-BO5 - collect multiple screenshots
        if selected_format in ["BO2", "BO3", "BO4", "BO5"] and attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            print(f"{selected_format} detected - collecting screenshots")
            await self.handle_multi_map_upload(message, bot, selected_format, clan_name)
            return
        
        # Save to JSON file
        highlights_data = self.load_highlights_data()
        highlight_id = str(len(highlights_data) + 1)
        
        highlight_entry = {
            "id": highlight_id,
            "user_id": str(message.author.id),
            "username": message.author.display_name,
            "match_format": selected_format,
            "clan_name": clan_name,
            "description": message.content if message.content else "No description provided.",
            "filename": attachment.filename,
            "file_size": attachment.size,
            "timestamp": datetime.now().isoformat()
        }
        
        highlights_data[highlight_id] = highlight_entry
        print(f"Saving highlight entry: {highlight_entry}")
        self.save_highlights_data(highlights_data)
        
        # Create highlight embed
        embed = discord.Embed(
            title="New Scrim Highlight",
            description=message.content if message.content else "No description provided.",
            color=0x9d4edd,  # Purple color
            timestamp=datetime.now()
        )
        
        embed.set_author(
            name=f"{message.author.display_name}'s Highlight",
            icon_url=message.author.display_avatar.url
        )
        
        # Add match format
        embed.add_field(
            name="Match Format",
            value=f"**{selected_format}** (Best of {selected_format[2]})",
            inline=True
        )
        
        # Add clan name
        embed.add_field(
            name="Opponent",
            value=f"**{clan_name}**",
            inline=True
        )
        
        embed.add_field(
            name="File Info", 
            value=f"Size: {attachment.size / (1024*1024):.1f}MB\nType: {attachment.filename.split('.')[-1].upper()}", 
            inline=True
        )
        embed.set_footer(text="Zero Remorse • Scrim Highlights")
        
        try:
            # Send the highlight to the channel
            highlight_msg = await highlights_channel.send(embed=embed, file=await attachment.to_file())
            
            # Add reactions for engagement
            reactions = ['🔥', '💯', '👏', '🎯']
            for reaction in reactions:
                await highlight_msg.add_reaction(reaction)
            
            # Confirm to user in DM
            success_embed = discord.Embed(
                title="Highlight Posted Successfully!",
                description=f"Your scrim highlight has been posted in {highlights_channel.mention}",
                color=0x00ff00
            )
            await message.reply(embed=success_embed)
            
            # Clean up stored data
            if hasattr(bot, 'user_match_formats') and message.author.id in bot.user_match_formats:
                del bot.user_match_formats[message.author.id]
            if hasattr(bot, 'user_clan_names') and message.author.id in bot.user_clan_names:
                del bot.user_clan_names[message.author.id]
            
        except Exception as e:
            await message.reply(f"Error posting highlight: {str(e)}")
    
    async def process_highlight_upload(self, message):
        """Process uploaded highlight files"""
        if not message.attachments:
            return
        
        # Check if user has pending highlight info
        if not hasattr(self.bot, 'pending_highlights'):
            return
        
        user_id = message.author.id
        if user_id not in self.bot.pending_highlights:
            return
        
        highlight_info = self.bot.pending_highlights[user_id]
        
        # Check if the attachment is a video file
        valid_extensions = ['.mp4', '.mov', '.avi', '.gif', '.mkv', '.webm']
        attachment = message.attachments[0]
        
        if not any(attachment.filename.lower().endswith(ext) for ext in valid_extensions):
            await message.reply("Please upload a valid video file (.mp4, .mov, .avi, .gif, .mkv, .webm)")
            return
        
        # Check file size (50MB limit)
        if attachment.size > 50 * 1024 * 1024:  # 50MB in bytes
            await message.reply("File too large! Please keep highlights under 50MB.")
            return
        
        # Create highlight embed
        embed = discord.Embed(
            title=f"{highlight_info['title']}",
            description=highlight_info['description'] or "No description provided.",
            color=0x9d4edd,  # Purple color
            timestamp=datetime.now()
        )
        
        embed.set_author(
            name=f"{message.author.display_name}'s Highlight",
            icon_url=message.author.display_avatar.url
        )
        
        if highlight_info['map_name']:
            embed.add_field(name="Map", value=highlight_info['map_name'], inline=True)
        
        if highlight_info['players_involved']:
            embed.add_field(name="Players", value=highlight_info['players_involved'], inline=True)
        
        embed.add_field(name="File Info", value=f"Size: {attachment.size / (1024*1024):.1f}MB", inline=True)
        embed.set_footer(text="Zero Remorse • Scrim Highlights")
        
        # Send the highlight to the channel
        await message.channel.send(embed=embed, file=await attachment.to_file())
        
        # Add reactions for engagement
        sent_message = await message.channel.fetch_message((await message.channel.history(limit=1).__anext__()).id)
        reactions = ['🔥', '💯', '👏', '🎯']
        for reaction in reactions:
            await sent_message.add_reaction(reaction)
        
        # Clean up pending highlights
        del self.bot.pending_highlights[user_id]
        
        # Delete the original message to keep channel clean
        try:
            await message.delete()
        except:
            pass  # Ignore if can't delete
        
        await message.channel.send(f"{message.author.mention} Your highlight has been posted!", delete_after=5)
    
    async def handle_multi_map_upload(self, message, bot, selected_format, clan_name):
        """Handle multi-map screenshot collection for BO2-BO5"""
        try:
            # Initialize multi-map data storage
            if not hasattr(bot, 'user_multi_map_data'):
                bot.user_multi_map_data = {}
            
            user_id = message.author.id
            
            # Initialize or get existing multi-map data for this user
            if user_id not in bot.user_multi_map_data:
                bot.user_multi_map_data[user_id] = {
                    "screenshots": [],
                    "clan_name": clan_name,
                    "match_format": selected_format
                }
            
            # Add the screenshot to the collection
            attachment = message.attachments[0]
            screenshot_data = await attachment.read()
            
            bot.user_multi_map_data[user_id]["screenshots"].append({
                "filename": attachment.filename,
                "data": screenshot_data
            })
            
            screenshot_count = len(bot.user_multi_map_data[user_id]["screenshots"])
            format_num = int(selected_format[2])
            max_maps = (format_num + 1) // 2  # BO3=2, BO5=3, etc.
            
            if screenshot_count < max_maps:
                await message.reply(f"**Screenshot {screenshot_count} received!**\n\nSend another screenshot if you have it, or type **'done'** to process the {selected_format} match.\nType **'cancel'** to abort this process.")
            else:
                # Max screenshots reached
                await message.reply(f"**Screenshot {screenshot_count} received!**\n\nType **'done'** to process the {selected_format} match.\nType **'cancel'** to abort this process.")
            
        except Exception as e:
            print(f"Error handling {selected_format} upload: {e}")
            await message.reply("Error uploading screenshot. Please try again.")
    
    async def process_multi_map_screenshots(self, message, bot):
        """Process collected multi-map screenshots using OCR"""
        try:
            user_id = message.author.id
            multi_map_data = bot.user_multi_map_data.get(user_id)
            
            if not multi_map_data or not multi_map_data["screenshots"]:
                await message.reply("No screenshots found. Please start over.")
                return
            
            screenshots = multi_map_data["screenshots"]
            clan_name = multi_map_data["clan_name"]
            match_format = multi_map_data["match_format"]
            
            await message.reply(f"**Processing {len(screenshots)} screenshot(s) for {match_format} match...**")
            
            # Import and use the appropriate OCR handler based on format
            if match_format == "BO2":
                from scrim_highlight_ocr import BO2OCRHandler
                ocr_handler = BO2OCRHandler()
                await ocr_handler.process_bo2_match(message, bot, screenshots, clan_name, user_id)
            elif match_format == "BO3":
                from scrim_highlight_ocr import BO3OCRHandler
                ocr_handler = BO3OCRHandler()
                await ocr_handler.process_bo3_match(message, bot, screenshots, clan_name, user_id)
            elif match_format == "BO4":
                from scrim_highlight_ocr import BO4OCRHandler
                ocr_handler = BO4OCRHandler()
                await ocr_handler.process_bo4_match(message, bot, screenshots, clan_name, user_id)
            elif match_format == "BO5":
                from scrim_highlight_ocr import BO5OCRHandler
                ocr_handler = BO5OCRHandler()
                await ocr_handler.process_bo5_match(message, bot, screenshots, clan_name, user_id)
            
            # Clean up multi-map data
            if user_id in bot.user_multi_map_data:
                del bot.user_multi_map_data[user_id]
            
            # Clean up other stored data
            if hasattr(bot, 'user_match_formats') and user_id in bot.user_match_formats:
                del bot.user_match_formats[user_id]
            if hasattr(bot, 'user_clan_names') and user_id in bot.user_clan_names:
                del bot.user_clan_names[user_id]
                
        except Exception as e:
            print(f"Error processing {match_format} screenshots: {e}")
            import traceback
            traceback.print_exc()
            await message.reply("Error processing screenshots. Please try again.")

def setup_scrim_highlights(bot):
    """Setup scrim highlights functionality"""
    handler = ScrimHighlightHandler(bot)
    
    @bot.event
    async def on_message(message):
        """Handle messages for highlight uploads"""
        if message.author.bot:
            return
        
        # Handle DM messages from users with Valom role
        if isinstance(message.channel, discord.DMChannel):
            await handler.process_dm_highlight(message, bot)
            return
        
        # Only process in the designated channel (old functionality - keeping for backup)
        if message.channel.id != int(os.getenv('CHANNEL_ID')):
            return
        
        # Only process messages with attachments (since we can't read message content)
        if not message.attachments:
            return
        
        # Process highlight uploads
        await handler.process_highlight_upload(message)
    
    return handler