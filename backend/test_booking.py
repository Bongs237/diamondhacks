import asyncio
from dotenv import load_dotenv

load_dotenv()

from agents.browser_runner import run_event_booking


async def main():
    print("Starting booking agent — this takes 1-3 minutes.")
    print("Open the live URL below to watch the browser in real time:\n")

    result = await run_event_booking(
        booking_url="https://www.amctheatres.com/movie-theatres/san-diego/amc-la-jolla-12",
        event_title="Movie Night at AMC La Jolla 12",
        when="Wed. Apr 08, 2026",
        party_size=2,
        allow_payment=False,
        on_live_url=lambda url: print(f"  Live view: {url}\n"),
    )
    print(result.model_dump_json(indent=2))


asyncio.run(main())
