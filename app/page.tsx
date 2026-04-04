"use client"

import { useState } from "react";

export default function Home() {

  const [phoneNumber, setPhoneNumber] = useState("");

  const handleSubmit = () => {
    console.log(phoneNumber);
  };

  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans">
      <h1 className="text-3xl font-bold">To start, enter your phone number below</h1>

      <div className="flex flex-row gap-2 pt-5">
        <input
          type="tel"
          pattern="[0-9]*"
          placeholder="Phone Number"
          className="border-2 border-gray-300 rounded-md p-2"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
        />
        <button className="bg-blue-500 text-white p-2 rounded-md" onClick={handleSubmit}>Submit</button>
      </div>
    </div>
  );
}
