import discord
from discord.ext import commands
import os
import google.generativeai as genai
from PIL import Image
import io
import base64
from datetime import datetime
import json

class ScoreConfirmationView(discord.ui.View):
    def __init__(self, extracted_data, user_id, original_message, bot=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.extracted_data = extracted_data
        self.user_id = user_id
        self.original_message = original_message
        self.bot = bot
    
    @discord.ui.button(label="Correct", style=discord.ButtonStyle.success)
    async def confirm_correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation!", ephemeral=True)
            return
        
        # Defer the response to prevent timeout
        await interaction.response.defer()
        
        # Save the confirmed data
        await self.save_confirmed_data(interaction)
        
        # Post screenshot to the designated channel
        await self.post_to_channel(interaction)
        
        # Update the message with comprehensive confirmation
        embed = discord.Embed(
            title="Match Data Saved Successfully!",
            description="Your Valorant match has been confirmed and saved to the database, and posted to the channel!",
            color=0x00ff00
        )
        
        # Add summary of saved data
        embed.add_field(
            name="Match Result", 
            value=f"{self.extracted_data.get('our_score', 0)} - {self.extracted_data.get('enemy_score', 0)} ({self.extracted_data.get('result', 'Unknown')})",
            inline=False
        )
        
        embed.set_footer(text="Data has been added to the scrim highlights database and posted to channel")
        await interaction.edit_original_response(embed=embed, view=None)
    
    @discord.ui.button(label="Incorrect", style=discord.ButtonStyle.danger)
    async def confirm_incorrect(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Score Rejected",
            description="Please try uploading the screenshot again or contact an admin if the OCR keeps failing.",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def save_confirmed_data(self, interaction):
        """Save the confirmed score data to JSON"""
        try:
            # Get clan name from stored data
            clan_name = "Unknown"
            if self.bot and hasattr(self.bot, 'user_ocr_data') and self.user_id in self.bot.user_ocr_data:
                clan_name = self.bot.user_ocr_data[self.user_id].get("clan_name", "Unknown")
            
            # Load existing data
            json_file = "scrim_highlight.json"
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        data = {}
                    else:
                        data = json.loads(content)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}
            
            # Get upload type from stored data
            upload_type = "scrim"  # Default
            if hasattr(self.bot, 'user_ocr_data') and self.user_id in self.bot.user_ocr_data:
                upload_type = self.bot.user_ocr_data[self.user_id].get("upload_type", "scrim")
            
            # Create new entry
            highlight_id = str(len(data) + 1)
            entry = {
                "id": highlight_id,
                "user_id": str(self.user_id),
                "username": interaction.user.display_name,
                "match_format": self.extracted_data.get("match_format", "BO1"),
                "upload_type": upload_type,
                "clan_name": clan_name,
                "our_score": self.extracted_data.get("our_score", 0),
                "enemy_score": self.extracted_data.get("enemy_score", 0),
                "result": self.extracted_data.get("result", "Unknown"),
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "OCR"
            }
            
            data[highlight_id] = entry
            
            # Save to file
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"Saved confirmed OCR data: {entry}")
            
        except Exception as e:
            print(f"Error saving confirmed data: {e}")
    
    async def post_to_channel(self, interaction):
        """Post the screenshot to the designated channel with the formatted message"""
        try:
            if not self.bot:
                print("Bot instance not available for posting to channel")
                return
                
            # Get upload type and determine channel
            upload_type = "scrim"  # Default
            clan_name = "Unknown"
            if hasattr(self.bot, 'user_ocr_data') and self.user_id in self.bot.user_ocr_data:
                ocr_data = self.bot.user_ocr_data[self.user_id]
                clan_name = ocr_data.get("clan_name", "Unknown")
                upload_type = ocr_data.get("upload_type", "scrim")
            
            # Get the appropriate channel ID based on upload type
            if upload_type == "tournament":
                channel_id = int(os.getenv('TOURNAMENT_HIGHLIGHTS_CHANNEL_ID'))
                channel_type_name = "tournament highlights"
            else:
                channel_id = int(os.getenv('SCRIM_HIGHLIGHTS_CHANNEL_ID'))
                channel_type_name = "scrim highlights"
                
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                print(f"{channel_type_name.title()} channel with ID {channel_id} not found!")
                return
            
            # Create the message format based on match result and format
            match_format = self.extracted_data.get("match_format", "BO1")
            result = self.extracted_data.get("result", "unknown").lower()
            
            if match_format == "BO1":
                # For BO1, check actual scores to determine result including draws
                our_score = self.extracted_data.get("our_score", 0)
                enemy_score = self.extracted_data.get("enemy_score", 0)
                
                if our_score > enemy_score:
                    result_text = "1-0 Win"
                elif enemy_score > our_score:
                    result_text = "0-1 Lose"
                elif our_score == enemy_score:
                    result_text = f"{our_score}-{enemy_score} Draw"
                else:
                    result_text = f"{our_score}-{enemy_score} Unknown"
            else:
                # For BO2-BO5, use actual match scores
                our_score = self.extracted_data.get("our_score", 0)
                enemy_score = self.extracted_data.get("enemy_score", 0)
                result_text = f"{our_score}-{enemy_score}"
            
            # Get total wins, losses, and draws count
            total_wins, total_losses, total_draws = await self.get_win_loss_draw_counts()
            
            # Create the message text in the requested format
            message_text = f"GG {clan_name}\n{match_format}\n{result_text}\nWins - {total_wins}\nLoses - {total_losses}\nDraws - {total_draws}"
            
            # Get the original screenshot from the DM message
            if self.original_message and self.original_message.attachments:
                attachment = self.original_message.attachments[0]
                
                # Download the image
                image_data = await attachment.read()
                
                # Create a discord file from the image data
                discord_file = discord.File(
                    io.BytesIO(image_data), 
                    filename=f"scrim_highlight_{self.user_id}_{attachment.filename}"
                )
                
                # Post to channel
                await channel.send(content=message_text, file=discord_file)
                print(f"Posted screenshot to channel #{channel.name} with message: {message_text}")
            else:
                print("No screenshot attachment found in original message")
                
        except Exception as e:
            print(f"Error posting to channel: {e}")
    
    async def get_win_loss_draw_counts(self):
        """Get the current total wins, losses, and draws count from JSON file"""
        try:
            json_file = "scrim_highlight.json"
            
            # Read existing data
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        data = {}
                    else:
                        data = json.loads(content)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}
            
            # Count wins, losses, and draws from all entries (including the current one that was just saved)
            wins_count = 0
            losses_count = 0
            draws_count = 0
            
            for entry_id, entry in data.items():
                if isinstance(entry, dict):
                    result = entry.get("result", "").lower()
                    if result == "win":
                        wins_count += 1
                        print(f"Counting win from entry {entry_id}: {entry.get('clan_name', 'Unknown')}")
                    elif result == "defeat":
                        losses_count += 1
                        print(f"Counting loss from entry {entry_id}: {entry.get('clan_name', 'Unknown')}")
                    elif result == "draw":
                        draws_count += 1
                        print(f"Counting draw from entry {entry_id}: {entry.get('clan_name', 'Unknown')}")
            
            print(f"Total wins: {wins_count}, Total losses: {losses_count}, Total draws: {draws_count}")
            return wins_count, losses_count, draws_count
            
        except Exception as e:
            print(f"Error counting wins/losses: {e}")
            return 0, 0, 0

class ValOCRHandler:
    def __init__(self):
        # Configure Gemini API
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    async def process_valorant_screenshot(self, message, bot, match_format="BO1"):
        """Process Valorant screenshot using OCR"""
        print(f"Processing Valorant screenshot for {message.author.display_name}")
        
        if not message.attachments:
            await message.reply("Please attach a Valorant screenshot!")
            return
        
        attachment = message.attachments[0]
        
        # Check if it's an image
        if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
            await message.reply("Please upload an image file (.png, .jpg, .jpeg, .gif)")
            return
        
        try:
            # Download and process the image
            image_data = await attachment.read()
            image = Image.open(io.BytesIO(image_data))
            
            # Extract score using Gemini
            extracted_data = await self.extract_score_with_gemini(image, match_format)
            
            if not extracted_data:
                await message.reply("Could not extract score from the screenshot. Please try again or contact an admin.")
                return
            
            # Get clan name from stored data
            clan_name = "Unknown"
            if hasattr(bot, 'user_ocr_data') and message.author.id in bot.user_ocr_data:
                clan_name = bot.user_ocr_data[message.author.id].get("clan_name", "Unknown")
            
            # Create confirmation embed
            embed = discord.Embed(
                title="Score Extraction Results",
                description="Please confirm if the extracted information is correct:",
                color=0xffa500
            )
            
            embed.add_field(
                name="Match Format",
                value=extracted_data.get("match_format", "BO1"),
                inline=True
            )
            
            embed.add_field(
                name="Opponent Clan",
                value=clan_name,
                inline=True
            )
            
            embed.add_field(
                name="Our Score",
                value=str(extracted_data.get("our_score", "Unknown")),
                inline=True
            )
            
            embed.add_field(
                name="Enemy Score", 
                value=str(extracted_data.get("enemy_score", "Unknown")),
                inline=True
            )
            
            embed.add_field(
                name="Result",
                value=extracted_data.get("result", "Unknown"),
                inline=True
            )
            
            embed.set_footer(text="Click 'Correct' to save or 'Incorrect' to reject")
            
            # Send confirmation with buttons
            view = ScoreConfirmationView(extracted_data, message.author.id, message, bot)
            await message.reply(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error processing screenshot: {e}")
            await message.reply(f"Error processing screenshot: {str(e)}")
    
    async def extract_score_with_gemini(self, image, match_format):
        """Extract score from Valorant screenshot using Gemini Vision API"""
        try:
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # Create simplified prompt for BO1 (score only)
            prompt = f"""
            Analyze this Valorant end-game screenshot and extract ONLY the match score and result.
            
            INSTRUCTIONS:
            1. Look at the score display in the upper center (format: number win/defeat number)
            2. The win/defeat text might be in English (WIN/DEFEAT) or Chinese (胜利/失败)
            3. Extract the round scores (like 13-10, 13-7, etc.)
            4. Determine if we won or lost based on the win/defeat text
            
            Return ONLY the JSON with this exact format:
            {{
                "our_score": number,
                "enemy_score": number,
                "result": "win" or "defeat",
                "match_format": "{match_format}"
            }}
            
            Example: If the score shows "13 VICTORY 10", return:
            {{"our_score": 13, "enemy_score": 10, "result": "win", "match_format": "{match_format}"}}
            """
            
            # Send to Gemini with async/await and timeout handling
            import asyncio
            
            async def run_gemini_request():
                # Run the synchronous Gemini call in a thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.model.generate_content([prompt, image])
                )
            
            # Set a timeout for the request
            try:
                response = await asyncio.wait_for(run_gemini_request(), timeout=15.0)
                
                # Parse the response
                response_text = response.text.strip()
                print(f"Gemini response: {response_text}")
                
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    extracted_data = json.loads(json_str)
                    return extracted_data
                else:
                    print("No valid JSON found in Gemini response")
                    return None
                    
            except asyncio.TimeoutError:
                print("Timeout processing Gemini request")
                return None
                
        except Exception as e:
            print(f"Error with Gemini API: {e}")
            return None

class BO2OCRHandler:
    def __init__(self):
        # Configure Gemini API
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    async def process_bo2_match(self, message, bot, screenshots, clan_name, user_id, upload_type='scrim'):
        """Process multiple screenshots for BO2 match"""
        try:
            # Store instance variables for later use
            self.bot = bot
            self.clan_name = clan_name
            self.user_id = user_id
            self.upload_type = upload_type
            self.screenshots = screenshots  # Store for posting later
            
            # Process each screenshot to get individual map results
            map_results = []
            
            for i, screenshot in enumerate(screenshots):
                print(f"Processing screenshot {i+1}/{len(screenshots)}")
                
                # Create image from screenshot data
                image = Image.open(io.BytesIO(screenshot["data"]))
                
                # Extract result from this map
                map_data = await self.extract_map_result(image, i+1)
                if map_data:
                    map_results.append(map_data)
                
                # Add delay between requests to prevent API overload
                if i < len(screenshots) - 1:  # Don't delay after the last screenshot
                    import asyncio
                    await asyncio.sleep(2)  # 2 second delay between screenshots
            
            if not map_results:
                await message.reply("Could not process any screenshots. Please try again.")
                return
            
            # Calculate overall BO2 result
            our_wins = sum(1 for result in map_results if result.get("result") == "win")
            enemy_wins = len(map_results) - our_wins
            
            # Determine overall match result
            if our_wins > enemy_wins:
                overall_result = "win"
                score_text = f"{our_wins}-{enemy_wins} Win"
            elif enemy_wins > our_wins:
                overall_result = "defeat"
                score_text = f"{our_wins}-{enemy_wins} Lose" 
            else:
                overall_result = "draw"
                score_text = f"{our_wins}-{enemy_wins} Draw"
            
            # Create combined data (no ACS data)
            combined_data = {
                "match_format": "BO2",
                "our_score": our_wins,
                "enemy_score": enemy_wins,
                "result": overall_result,
                "map_results": map_results
            }
            
            # Create confirmation view
            view = BO2ConfirmationView(combined_data, user_id, message, bot, screenshots, clan_name)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="BO2 Match Results",
                description="Please confirm if the extracted information is correct:",
                color=0xffa500
            )
            
            embed.add_field(name="Match Format", value="BO2", inline=True)
            embed.add_field(name="Opponent Clan", value=clan_name, inline=True)
            embed.add_field(name="Overall Result", value=score_text, inline=True)
            
            # Add individual map results
            for i, result in enumerate(map_results):
                map_result = "Win" if result.get("result") == "win" else "Loss"
                embed.add_field(
                    name=f"Map {i+1}",
                    value=f"{result.get('our_score', 0)}-{result.get('enemy_score', 0)} ({map_result})",
                    inline=True
                )
            
            embed.set_footer(text="Click 'Correct' to save or 'Incorrect' to reject")
            
            await message.reply(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error processing BO2 match: {e}")
            import traceback
            traceback.print_exc()
            await message.reply("Error processing BO2 match. Please try again.")
    
    async def extract_map_result(self, image, map_number):
        """Extract result from a single map screenshot"""
        try:
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # Create simplified prompt for individual map (score only)
            prompt = f"""
            Analyze this Valorant end-game screenshot for Map {map_number} and extract ONLY the match score and result.
            
            INSTRUCTIONS:
            1. Look at the score display in the upper center (format: number win/defeat number)
            2. Determine if we won or lost based on the win/defeat text
            3. Extract the round scores (like 13-10, 13-7, etc.)
            
            Return ONLY the JSON with this exact format:
            {{
                "our_score": number,
                "enemy_score": number,
                "result": "win" or "defeat"
            }}
            
            Example: If the score shows "13 VICTORY 10", return:
            {{"our_score": 13, "enemy_score": 10, "result": "win"}}
            """
            
            # Send to Gemini with async/await and timeout handling
            import asyncio
            
            async def run_gemini_request():
                # Run the synchronous Gemini call in a thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.model.generate_content([prompt, image])
                )
            
            # Set a timeout for the request
            try:
                response = await asyncio.wait_for(run_gemini_request(), timeout=30.0)
                response_text = response.text.strip()
                print(f"Map {map_number} Gemini response: {response_text}")
                
                # Parse JSON response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    return json.loads(json_str)
                else:
                    print(f"No valid JSON found for map {map_number}")
                    return None
                    
            except asyncio.TimeoutError:
                print(f"Timeout processing map {map_number}")
                return None
                
        except Exception as e:
            print(f"Error extracting map {map_number} result: {e}")
            return None

class BO2ConfirmationView(discord.ui.View):
    def __init__(self, combined_data, user_id, original_message, bot, screenshots, clan_name):
        super().__init__(timeout=300)
        self.combined_data = combined_data
        self.user_id = user_id
        self.original_message = original_message
        self.bot = bot
        self.screenshots = screenshots
        self.clan_name = clan_name
    
    @discord.ui.button(label="Correct", style=discord.ButtonStyle.success)
    async def confirm_correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Save data and post to channel
        await self.save_and_post_bo2(interaction)
        
        embed = discord.Embed(
            title="BO2 Match Saved Successfully!",
            description="Your BO2 match has been saved and posted to the channel!",
            color=0x00ff00
        )
        
        await interaction.edit_original_response(embed=embed, view=None)
    
    @discord.ui.button(label="Incorrect", style=discord.ButtonStyle.danger)
    async def confirm_incorrect(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="BO2 Match Rejected",
            description="Please try uploading the screenshots again.",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def save_and_post_bo2(self, interaction):
        """Save BO2 data and post to channel with both screenshots"""
        try:
            # Save to JSON file
            json_file = "scrim_highlight.json"
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        data = {}
                    else:
                        data = json.loads(content)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}
            
            # Create new entry
            highlight_id = str(len(data) + 1)
            entry = {
                "id": highlight_id,
                "user_id": str(self.user_id),
                "username": interaction.user.display_name,
                "match_format": "BO2",
                "upload_type": getattr(self, 'upload_type', 'scrim'),
                "clan_name": self.clan_name,
                "our_score": self.combined_data.get("our_score", 0),
                "enemy_score": self.combined_data.get("enemy_score", 0),
                "result": self.combined_data.get("result", "Unknown"),
                "map_results": self.combined_data.get("map_results", []),
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "OCR"
            }
            
            data[highlight_id] = entry
            
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Post to channel
            await self.post_bo2_to_channel(entry)
            
        except Exception as e:
            print(f"Error saving BO2 data: {e}")
    
    async def post_bo2_to_channel(self, entry):
        """Post BO2 match to channel with both screenshots"""
        try:
            # Get the appropriate channel based on upload type
            upload_type = entry.get("upload_type", "scrim")
            if upload_type == "tournament":
                channel_id = int(os.getenv('TOURNAMENT_HIGHLIGHTS_CHANNEL_ID'))
                channel_type_name = "tournament highlights"
            else:
                channel_id = int(os.getenv('SCRIM_HIGHLIGHTS_CHANNEL_ID'))
                channel_type_name = "scrim highlights"
                
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                print(f"{channel_type_name.title()} channel not found: {channel_id}")
                return
            
            # Calculate wins/losses/draws
            wins_count = 0
            losses_count = 0
            draws_count = 0
            
            json_file = "scrim_highlight.json"
            try:
                with open(json_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        for e in data.values():
                            if isinstance(e, dict):
                                if e.get("result") == "win":
                                    wins_count += 1
                                elif e.get("result") == "defeat":
                                    losses_count += 1
                                elif e.get("result") == "draw":
                                    draws_count += 1
            except:
                pass
            
            # Create message text
            result = entry.get("result", "unknown").lower()
            our_score = entry.get("our_score", 0)
            enemy_score = entry.get("enemy_score", 0)
            
            if result == "win":
                result_text = f"{our_score}-{enemy_score} Win"
            elif result == "draw":
                result_text = f"{our_score}-{enemy_score} Draw"
            else:
                result_text = f"{our_score}-{enemy_score} Lose"
            
            message_text = f"GG {self.clan_name}\nBO2\n{result_text}\nWins - {wins_count}\nLoses - {losses_count}\nDraws - {draws_count}"
            
            # Create Discord files from screenshots
            files = []
            for i, screenshot in enumerate(self.screenshots):
                file_data = io.BytesIO(screenshot["data"])
                discord_file = discord.File(file_data, filename=f"bo2_map{i+1}_{screenshot['filename']}")
                files.append(discord_file)
            
            # Post message with all screenshots
            await channel.send(content=message_text, files=files)
            print(f"Posted BO2 match to channel with {len(files)} screenshots")
            
        except Exception as e:
            print(f"Error posting BO2 to channel: {e}")
            import traceback
            traceback.print_exc()

class BO3OCRHandler:
    def __init__(self):
        # Configure Gemini API
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    async def process_bo3_match(self, message, bot, screenshots, clan_name, user_id, upload_type):
        """Process multiple screenshots for BO3 match"""
        try:
            # Process each screenshot to get individual map results
            map_results = []
            
            # Send progress message
            progress_msg = await message.reply(f"🔄 Processing {len(screenshots)} screenshots for BO3 match...")
            
            for i, screenshot in enumerate(screenshots):
                print(f"Processing screenshot {i+1}/{len(screenshots)}")
                
                # Update progress
                if progress_msg:
                    try:
                        await progress_msg.edit(content=f"🔄 Processing screenshot {i+1}/{len(screenshots)}...")
                    except:
                        pass  # Ignore edit failures
                
                # Create image from screenshot data
                image = Image.open(io.BytesIO(screenshot["data"]))
                
                # Extract result from this map
                map_data = await self.extract_map_result(image, i+1)
                if map_data:
                    map_results.append(map_data)
                
                # Add delay between requests to prevent API overload
                if i < len(screenshots) - 1:
                    import asyncio
                    await asyncio.sleep(2)
            
            # Clean up progress message
            if progress_msg:
                try:
                    await progress_msg.delete()
                except:
                    pass
            
            if not map_results:
                await message.reply("Could not process any screenshots. Please try again.")
                return
            
            # Calculate overall BO3 result
            our_wins = sum(1 for result in map_results if result.get("result") == "win")
            enemy_wins = len(map_results) - our_wins
            
            # Determine overall match result
            if our_wins > enemy_wins:
                overall_result = "win"
                score_text = f"{our_wins}-{enemy_wins} Win"
            elif enemy_wins > our_wins:
                overall_result = "defeat"
                score_text = f"{our_wins}-{enemy_wins} Lose"
            else:
                overall_result = "draw"
                score_text = f"{our_wins}-{enemy_wins} Draw"
            
            # Create combined data
            combined_data = {
                "match_format": "BO3",
                "our_score": our_wins,
                "enemy_score": enemy_wins,
                "result": overall_result,
                "map_results": map_results
            }
            
            # Create confirmation view
            view = MultiMapConfirmationView(combined_data, user_id, message, bot, screenshots, clan_name, upload_type)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="BO3 Match Results",
                description="Please confirm if the extracted information is correct:",
                color=0xffa500
            )
            
            embed.add_field(name="Match Format", value="BO3", inline=True)
            embed.add_field(name="Opponent Clan", value=clan_name, inline=True)
            embed.add_field(name="Overall Result", value=score_text, inline=True)
            
            # Add individual map results
            for i, result in enumerate(map_results):
                map_result = "Win" if result.get("result") == "win" else "Loss"
                embed.add_field(
                    name=f"Map {i+1}",
                    value=f"{result.get('our_score', 0)}-{result.get('enemy_score', 0)} ({map_result})",
                    inline=True
                )
            
            embed.set_footer(text="Click 'Correct' to save or 'Incorrect' to reject")
            
            await message.reply(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error processing BO3 match: {e}")
            import traceback
            traceback.print_exc()
            await message.reply("Error processing BO3 match. Please try again.")
    
    async def extract_map_result(self, image, map_number):
        """Extract result from a single map screenshot - BO3 handler"""
        try:
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # Create simplified prompt for individual map (score only)
            prompt = f"""
            Analyze this Valorant end-game screenshot for Map {map_number} and extract ONLY the match score and result.
            
            INSTRUCTIONS:
            1. Look at the score display in the upper center (format: number win/defeat number)
            2. Determine if we won or lost based on the win/defeat text
            3. Extract the round scores (like 13-10, 13-7, etc.)
            
            Return ONLY the JSON with this exact format:
            {{
                "our_score": number,
                "enemy_score": number,
                "result": "win" or "defeat"
            }}
            
            Example: If the score shows "13 VICTORY 10", return:
            {{"our_score": 13, "enemy_score": 10, "result": "win"}}
            """
            
            # Send to Gemini with async/await and timeout handling
            import asyncio
            
            async def run_gemini_request():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.model.generate_content([prompt, image])
                )
            
            try:
                response = await asyncio.wait_for(run_gemini_request(), timeout=15.0)
                response_text = response.text.strip()
                print(f"Map {map_number} Gemini response: {response_text}")
                
                # Parse JSON response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    return json.loads(json_str)
                else:
                    print(f"No valid JSON found for map {map_number}")
                    return None
                    
            except asyncio.TimeoutError:
                print(f"Timeout processing map {map_number}")
                return None
                
        except Exception as e:
            print(f"Error extracting map {map_number} result: {e}")
            return None


class BO4OCRHandler:
    def __init__(self):
        # Configure Gemini API
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    async def process_bo4_match(self, message, bot, screenshots, clan_name, user_id, upload_type):
        """Process multiple screenshots for BO4 match"""
        try:
            # Process each screenshot to get individual map results
            map_results = []
            
            for i, screenshot in enumerate(screenshots):
                print(f"Processing screenshot {i+1}/{len(screenshots)}")
                
                # Create image from screenshot data
                image = Image.open(io.BytesIO(screenshot["data"]))
                
                # Extract result from this map
                map_data = await self.extract_map_result(image, i+1)
                if map_data:
                    map_results.append(map_data)
                
                # Add delay between requests to prevent API overload
                if i < len(screenshots) - 1:
                    import asyncio
                    await asyncio.sleep(2)
            
            if not map_results:
                await message.reply("Could not process any screenshots. Please try again.")
                return
            
            # Calculate overall BO4 result
            our_wins = sum(1 for result in map_results if result.get("result") == "win")
            enemy_wins = len(map_results) - our_wins
            
            # Determine overall match result
            if our_wins > enemy_wins:
                overall_result = "win"
                score_text = f"{our_wins}-{enemy_wins} Win"
            elif enemy_wins > our_wins:
                overall_result = "defeat"
                score_text = f"{our_wins}-{enemy_wins} Lose"
            else:
                overall_result = "draw"
                score_text = f"{our_wins}-{enemy_wins} Draw"
            
            # Create combined data
            combined_data = {
                "match_format": "BO4",
                "our_score": our_wins,
                "enemy_score": enemy_wins,
                "result": overall_result,
                "map_results": map_results
            }
            
            # Create confirmation view
            view = MultiMapConfirmationView(combined_data, user_id, message, bot, screenshots, clan_name, upload_type)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="BO4 Match Results",
                description="Please confirm if the extracted information is correct:",
                color=0xffa500
            )
            
            embed.add_field(name="Match Format", value="BO4", inline=True)
            embed.add_field(name="Opponent Clan", value=clan_name, inline=True)
            embed.add_field(name="Overall Result", value=score_text, inline=True)
            
            # Add individual map results
            for i, result in enumerate(map_results):
                map_result = "Win" if result.get("result") == "win" else "Loss"
                embed.add_field(
                    name=f"Map {i+1}",
                    value=f"{result.get('our_score', 0)}-{result.get('enemy_score', 0)} ({map_result})",
                    inline=True
                )
            
            embed.set_footer(text="Click 'Correct' to save or 'Incorrect' to reject")
            
            await message.reply(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error processing BO4 match: {e}")
            import traceback
            traceback.print_exc()
            await message.reply("Error processing BO4 match. Please try again.")
    
    async def extract_map_result(self, image, map_number):
        """Extract result from a single map screenshot - same as BO3"""
        try:
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # Create simplified prompt for individual map (score only)
            prompt = f"""
            Analyze this Valorant end-game screenshot for Map {map_number} and extract ONLY the match score and result.
            
            INSTRUCTIONS:
            1. Look at the score display in the upper center (format: number win/defeat number)
            2. Determine if we won or lost based on the win/defeat text
            3. Extract the round scores (like 13-10, 13-7, etc.)
            
            Return ONLY the JSON with this exact format:
            {{
                "our_score": number,
                "enemy_score": number,
                "result": "win" or "defeat"
            }}
            
            Example: If the score shows "13 VICTORY 10", return:
            {{"our_score": 13, "enemy_score": 10, "result": "win"}}
            """
            
            # Send to Gemini with async/await and timeout handling
            import asyncio
            
            async def run_gemini_request():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.model.generate_content([prompt, image])
                )
            
            try:
                response = await asyncio.wait_for(run_gemini_request(), timeout=30.0)
                response_text = response.text.strip()
                print(f"Map {map_number} Gemini response: {response_text}")
                
                # Parse JSON response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    return json.loads(json_str)
                else:
                    print(f"No valid JSON found for map {map_number}")
                    return None
                    
            except asyncio.TimeoutError:
                print(f"Timeout processing map {map_number}")
                return None
                
        except Exception as e:
            print(f"Error extracting map {map_number} result: {e}")
            return None


class BO5OCRHandler:
    def __init__(self):
        # Configure Gemini API
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    async def process_bo5_match(self, message, bot, screenshots, clan_name, user_id, upload_type):
        """Process multiple screenshots for BO5 match"""
        try:
            # Process each screenshot to get individual map results
            map_results = []
            
            for i, screenshot in enumerate(screenshots):
                print(f"Processing screenshot {i+1}/{len(screenshots)}")
                
                # Create image from screenshot data
                image = Image.open(io.BytesIO(screenshot["data"]))
                
                # Extract result from this map
                map_data = await self.extract_map_result(image, i+1)
                if map_data:
                    map_results.append(map_data)
                
                # Add delay between requests to prevent API overload
                if i < len(screenshots) - 1:
                    import asyncio
                    await asyncio.sleep(2)
            
            if not map_results:
                await message.reply("Could not process any screenshots. Please try again.")
                return
            
            # Calculate overall BO5 result
            our_wins = sum(1 for result in map_results if result.get("result") == "win")
            enemy_wins = len(map_results) - our_wins
            
            # Determine overall match result
            if our_wins > enemy_wins:
                overall_result = "win"
                score_text = f"{our_wins}-{enemy_wins} Win"
            elif enemy_wins > our_wins:
                overall_result = "defeat"
                score_text = f"{our_wins}-{enemy_wins} Lose"
            else:
                overall_result = "draw"
                score_text = f"{our_wins}-{enemy_wins} Draw"
            
            # Create combined data
            combined_data = {
                "match_format": "BO5",
                "our_score": our_wins,
                "enemy_score": enemy_wins,
                "result": overall_result,
                "map_results": map_results
            }
            
            # Create confirmation view
            view = MultiMapConfirmationView(combined_data, user_id, message, bot, screenshots, clan_name, upload_type)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="BO5 Match Results",
                description="Please confirm if the extracted information is correct:",
                color=0xffa500
            )
            
            embed.add_field(name="Match Format", value="BO5", inline=True)
            embed.add_field(name="Opponent Clan", value=clan_name, inline=True)
            embed.add_field(name="Overall Result", value=score_text, inline=True)
            
            # Add individual map results
            for i, result in enumerate(map_results):
                map_result = "Win" if result.get("result") == "win" else "Loss"
                embed.add_field(
                    name=f"Map {i+1}",
                    value=f"{result.get('our_score', 0)}-{result.get('enemy_score', 0)} ({map_result})",
                    inline=True
                )
            
            embed.set_footer(text="Click 'Correct' to save or 'Incorrect' to reject")
            
            await message.reply(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error processing BO5 match: {e}")
            import traceback
            traceback.print_exc()
            await message.reply("Error processing BO5 match. Please try again.")
    
    async def extract_map_result(self, image, map_number):
        """Extract result from a single map screenshot - same as BO3"""
        try:
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # Create simplified prompt for individual map (score only)
            prompt = f"""
            Analyze this Valorant end-game screenshot for Map {map_number} and extract ONLY the match score and result.
            
            INSTRUCTIONS:
            1. Look at the score display in the upper center (format: number win/defeat number)
            2. Determine if we won or lost based on the win/defeat text
            3. Extract the round scores (like 13-10, 13-7, etc.)
            
            Return ONLY the JSON with this exact format:
            {{
                "our_score": number,
                "enemy_score": number,
                "result": "win" or "defeat"
            }}
            
            Example: If the score shows "13 VICTORY 10", return:
            {{"our_score": 13, "enemy_score": 10, "result": "win"}}
            """
            
            # Send to Gemini with async/await and timeout handling
            import asyncio
            
            async def run_gemini_request():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.model.generate_content([prompt, image])
                )
            
            try:
                response = await asyncio.wait_for(run_gemini_request(), timeout=30.0)
                response_text = response.text.strip()
                print(f"Map {map_number} Gemini response: {response_text}")
                
                # Parse JSON response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    return json.loads(json_str)
                else:
                    print(f"No valid JSON found for map {map_number}")
                    return None
                    
            except asyncio.TimeoutError:
                print(f"Timeout processing map {map_number}")
                return None
                
        except Exception as e:
            print(f"Error extracting map {map_number} result: {e}")
            return None


class MultiMapConfirmationView(discord.ui.View):
    def __init__(self, combined_data, user_id, original_message, bot, screenshots, clan_name, upload_type):
        super().__init__(timeout=300)
        self.combined_data = combined_data
        self.user_id = user_id
        self.original_message = original_message
        self.bot = bot
        self.screenshots = screenshots
        self.clan_name = clan_name
        self.upload_type = upload_type
    
    @discord.ui.button(label="Correct", style=discord.ButtonStyle.success)
    async def confirm_correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Save data and post to channel
        await self.save_and_post_multimap(interaction)
        
        match_format = self.combined_data.get("match_format", "Multi-Map")
        embed = discord.Embed(
            title=f"{match_format} Match Saved Successfully!",
            description=f"Your {match_format} match has been saved and posted to the channel!",
            color=0x00ff00
        )
        
        await interaction.edit_original_response(embed=embed, view=None)
    
    @discord.ui.button(label="Incorrect", style=discord.ButtonStyle.danger)
    async def confirm_incorrect(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation!", ephemeral=True)
            return
        
        match_format = self.combined_data.get("match_format", "Multi-Map")
        embed = discord.Embed(
            title=f"{match_format} Match Rejected",
            description="Data discarded. Please try uploading again.",
            color=0xff0000
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def save_and_post_multimap(self, interaction):
        """Save multi-map match data and post to channel"""
        try:
            # Load existing data
            json_file = "scrim_highlight.json"
            if os.path.exists(json_file):
                with open(json_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {}
            
            # Create new entry
            highlight_id = str(len(data) + 1)
            
            entry = {
                "id": highlight_id,
                "user_id": str(self.user_id),
                "username": interaction.user.display_name,
                "match_format": self.combined_data.get("match_format", "Multi-Map"),
                "upload_type": self.upload_type,
                "clan_name": self.clan_name,
                "our_score": self.combined_data.get("our_score", 0),
                "enemy_score": self.combined_data.get("enemy_score", 0),
                "result": self.combined_data.get("result", "Unknown"),
                "map_results": self.combined_data.get("map_results", []),
                "timestamp": datetime.now().isoformat(),
                "extraction_method": "OCR"
            }
            
            data[highlight_id] = entry
            
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Post to channel - determine which channel based on upload_type
            if self.upload_type == "tournament":
                channel_id = int(os.getenv('TOURNAMENT_HIGHLIGHTS_CHANNEL_ID'))
            else:  # scrim
                channel_id = int(os.getenv('SCRIM_HIGHLIGHTS_CHANNEL_ID'))
            channel = self.bot.get_channel(channel_id)
            
            if channel:
                # Load wins/losses data for counters
                if os.path.exists(json_file):
                    with open(json_file, 'r') as f:
                        all_data = json.load(f)
                else:
                    all_data = {}
                
                # Count wins, losses, and draws for this user
                wins = sum(1 for item in all_data.values() 
                          if item.get('user_id') == str(self.user_id) and item.get('result') == 'win')
                losses = sum(1 for item in all_data.values() 
                            if item.get('user_id') == str(self.user_id) and item.get('result') == 'defeat')
                draws = sum(1 for item in all_data.values() 
                           if item.get('user_id') == str(self.user_id) and item.get('result') == 'draw')
                
                # Format match result
                match_format = self.combined_data.get("match_format", "Multi-Map")
                our_score = self.combined_data.get("our_score", 0)
                enemy_score = self.combined_data.get("enemy_score", 0)
                
                if self.combined_data.get("result") == "win":
                    result = "Win"
                elif self.combined_data.get("result") == "draw":
                    result = "Draw"
                else:
                    result = "Lose"
                
                message_content = f"GG {self.clan_name}\n{match_format}\n{our_score}-{enemy_score} {result}\nWins - {wins}\nLoses - {losses}\nDraws - {draws}"
                
                # Send screenshots to channel
                files = []
                for i, screenshot in enumerate(self.screenshots):
                    file_obj = discord.File(
                        io.BytesIO(screenshot["data"]), 
                        filename=f"{match_format}_screenshot_{i+1}.png"
                    )
                    files.append(file_obj)
                
                await channel.send(message_content, files=files)
                print(f"Posted {match_format} to channel with {len(files)} screenshots")
                
        except Exception as e:
            print(f"Error posting {self.combined_data.get('match_format', 'Multi-Map')} to channel: {e}")
            import traceback
            traceback.print_exc()


def setup_valorant_ocr(bot):
    """Setup Valorant OCR functionality"""
    ocr_handler = ValOCRHandler()
    
    # Add to existing DM handler logic
    return ocr_handler
