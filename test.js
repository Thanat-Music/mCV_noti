import express from 'express'
import { middleware } from '@line/bot-sdk'

const app = express()

const config = {
  channelSecret: 'YOUR_CHANNEL_SECRET'
}

app.post('/webhook', middleware(config), (req, res) => {
  req.body.events // webhook event objects from LINE Platform
  req.body.destination // user ID of the bot

})

app.listen(8080)