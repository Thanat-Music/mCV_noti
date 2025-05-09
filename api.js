// Import required modules
const express = require('express');
const { middleware } = require('@line/bot-sdk');
require('dotenv').config(); // Load environment variables

const app = express();

const config = {
    channelAccessToken: process.env.CHANNEL_ACCESS_TOKEN,
    channelSecret: process.env.CHANNEL_SECRET
  };
  
if (!config.channelAccessToken || !config.channelSecret) {
    console.error('ERROR: Missing environment variables. Check CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET.');
    process.exit(1);
}

// Webhook endpoint
app.post('/webhook', middleware(config), (req, res) => {
  const events = req.body.events;

  // Process each event
  events.forEach((event) => {
    if (event.type === 'message' && event.message.type === 'text') {
      const replyToken = event.replyToken;
      const userMessage = event.message.text;

      // Create a reply message
      const replyMessage = {
        type: 'text',
        text: `You said: ${userMessage}`
      };

      // Send the reply
      replyToUser(replyToken, replyMessage);
    }
  });

  // Respond to LINE with a 200 status code
  res.sendStatus(200);
});

// Function to send a reply to the user
// Function to send a reply to the user
function replyToUser(replyToken, message) {
    const axios = require('axios'); // Ensure axios is imported
    axios({
      method: 'post',
      url: 'https://api.line.me/v2/bot/message/reply',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.CHANNEL_ACCESS_TOKEN}`
      },
      data: {
        replyToken: replyToken,
        messages: [message]
      }
    })
      .then((response) => {
        console.log('Message sent successfully:', response.data);
      })
      .catch((error) => {
        console.error('Error sending message:', error.response ? error.response.data : error.message);
      });
    }

// Start the server
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
