**How our question changed.** We began with a simple expectation: wet roads slow traffic, so rain should push
Bengaluru's evening pollution peak later. The data said the opposite. When we compared rainy and dry evenings
in the same month and on the same kind of day, rainy evenings peaked lower and earlier, and they were already
cleaner at noon, before any rain fell. That changed our question from "how much does rain delay the peak?" to
"what does rainy weather go along with, and what can we honestly claim?". Our first SQL query on peak timing
showed that many evenings have no clear "8 PM" peak at all, because PM2.5 is often still rising at 23:00, so we
started reporting those evenings separately. Our first weekday table named Monday as the worst day; it turned
out that both Deepavalis fall on or next to a Monday, and a fair test showed no weekday stands out. The data
also changed our plan: only 5 stations reached 70% coverage, so we accepted 60% with a stricter rule for each
evening, and checking the holiday calendar against the government notification corrected two dates that a
holiday website had wrong.

**What we would do with better data.** More monitors in the outer city (Whitefield, Electronic City,
Yelahanka); rain gauges at each station instead of one city-centre point; hourly traffic counts or metro
ridership, so "traffic" becomes a measurement rather than an explanation; and several years of data, so a
"worst month" can be checked against other years.
