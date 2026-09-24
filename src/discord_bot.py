import discord
from discord.ext import commands
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def setup_discord_bot(token: str, music_dir: str) -> commands.Bot | None:
    if not token or token == "TUO_DISCORD_TOKEN":
        logger.info("Discord token non configurato, bot disabilitato.")
        return None
        
    intents = discord.Intents.default()
    intents.message_content = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        logger.info(f'Discord Bot connesso come {bot.user}')

    @bot.command()
    async def play(ctx, *, query: str):
        if not ctx.author.voice:
            await ctx.send("❌ Devi essere in un canale vocale per usare questo comando!")
            return
            
        channel = ctx.author.voice.channel
        await ctx.send(f"🔍 Cerco `{query}` nella libreria locale Navidrome...")
        
        search_terms = query.lower().split()
        found_file = None
        
        # Ricerca fuzzy semplice nel filesystem locale
        for root, _, files in os.walk(music_dir):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg')):
                    full_path = os.path.join(root, file).lower()
                    # Se tutti i termini (es. "queen", "bohemian") sono nel path (es. "/musica/queen/bohemian rhapsody.mp3")
                    if all(term in full_path for term in search_terms):
                        found_file = os.path.join(root, file)
                        break
            if found_file:
                break
                
        if not found_file:
            await ctx.send(f"❌ Nessun risultato trovato per `{query}`. Chiedi all'admin di scaricarla via Telegram!")
            return
            
        voice_client = ctx.voice_client
        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)
            
        if voice_client.is_playing():
            voice_client.stop()
            
        await ctx.send(f"🎵 Ora in riproduzione: **{Path(found_file).name}**")
        
        # FFmpegPCMAudio prende il file e lo invia a Discord
        source = discord.FFmpegPCMAudio(found_file)
        voice_client.play(source)

    @bot.command()
    async def stop(ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await ctx.send("⏹️ Riproduzione fermata.")
            
    @bot.command()
    async def leave(ctx):
        voice_client = ctx.voice_client
        if voice_client:
            await voice_client.disconnect()
            await ctx.send("👋 Alla prossima!")

    return bot
