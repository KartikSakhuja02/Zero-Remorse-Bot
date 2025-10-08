# 🚀 Zero Remorse Bot - Render Deployment Guide

## 📋 Prerequisites
- GitHub account
- Render account (free at render.com)
- Discord Bot Token
- Gemini API Key

## 🔧 Environment Variables (Set in Render Dashboard)

After creating your web service on Render, add these environment variables:

```
DISCORD_TOKEN=your_discord_bot_token_here
GUILD_ID=your_discord_server_id
CHANNEL_ID=your_main_channel_id  
VALOM_ROLE_ID=your_valom_role_id
SCRIM_HIGHLIGHTS_CHANNEL_ID=your_highlights_channel_id
GEMINI_API_KEY=your_gemini_api_key
BOT_PREFIX=!
PORT=8080
```

## 🌐 Render Deployment Steps

### 1. Push to GitHub
```bash
git add .
git commit -m "Deploy to Render"
git push origin main
```

### 2. Create Render Web Service
1. Go to [render.com](https://render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure settings:
   - **Name**: `zero-remorse-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: `Free`

### 3. Set Environment Variables
In your Render dashboard:
- Go to your service
- Click "Environment" tab
- Add all the environment variables listed above

### 4. Deploy
- Click "Deploy Latest Commit"
- Wait for deployment to complete
- Check logs for any errors

## 🔄 Keeping Bot Active (Free Tier)

The free tier sleeps after 15 minutes of inactivity. To keep it active:

1. **UptimeRobot** (Recommended):
   - Sign up at [uptimerobot.com](https://uptimerobot.com)
   - Add your Render URL as HTTP monitor
   - Set interval to 5 minutes

2. **Cron-job.org**:
   - Sign up at [cron-job.org](https://cron-job.org)
   - Create job to ping your Render URL every 5 minutes

## 📊 Monitoring

- **Render Logs**: Check deployment logs in Render dashboard
- **Discord**: Bot should show as online
- **Health Check**: Visit your Render URL to see "Bot is running!" message

## 🐛 Troubleshooting

### Bot Not Starting
- Check environment variables are set correctly
- Verify Discord token is valid
- Check Render build logs for errors

### Bot Going Offline
- Set up ping service (UptimeRobot)
- Check if free tier hours are exhausted
- Verify no errors in logs

### Commands Not Working
- Ensure bot has proper permissions in Discord server
- Check if GUILD_ID matches your server
- Verify role IDs are correct

## 💡 Tips

1. **Logs**: Always check Render logs for debugging
2. **Updates**: Push to GitHub to redeploy automatically
3. **Monitoring**: Set up uptime monitoring for 24/7 operation
4. **Backup**: Keep environment variables backed up securely

## 🆙 Upgrading

For true 24/7 operation without sleep:
- Upgrade to Render's **Starter Plan** ($7/month)
- Or use **Railway** ($5/month)
- Or **Heroku** ($7/month)

---

*Need help? Check the logs first, then verify all environment variables are set correctly.*