export default function handler(req, res) {
  const TITLES = [
    {p:"chorki", t:"Lifeline", dur:"1h 40m", days:12, img:"https://image.chorkicdn.com/uploads/images/2026/06/20/thumbnails_75c45f3483c9c9ac3cacb7fc1d26baf8_goplay_1200x675.jpg?w=1080&q=75", url:"https://www.chorki.com/movie/lifeline", synopsis:"How far would you go, and what would you risk for the one you love? What drives Ananya, a city girl, to this distant village."},
    {p:"chorki", t:"Domm", dur:"2h 7m", days:43, img:"https://image.chorkicdn.com/uploads/images/2026/05/20/thumbnails_9a17986cf1a558e41096ed09c653767d_goplay_1200x675.jpg?w=1080&q=75", url:"https://www.chorki.com/movie/domm", synopsis:"Noor, a man from a small town, gets the chance to go abroad through his job. But in an unfamiliar country, Noor faces danger."}
  ];

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Content-Type', 'application/json');
  
  res.status(200).json(TITLES);
}
