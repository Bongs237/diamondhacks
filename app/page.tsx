"use client";

import { useState } from "react";
import { Amatic_SC } from "next/font/google";

const amatic = Amatic_SC({
  subsets: ["latin"],
  weight: ["400", "700"],
});

function formatPhoneNumber(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function getRawDigits(value: string): string {
  return value.replace(/\D/g, "");
}

export default function Home() {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [error, setError] = useState("");
  const [touched, setTouched] = useState(false);

  const digits = getRawDigits(phoneNumber);

  const validate = (value: string): string => {
    const d = getRawDigits(value);
    if (d.length === 0) return "Phone number is required";
    if (d.length < 10) return "Phone number must be 10 digits";
    if (!/^[2-9]\d{2}[2-9]\d{6}$/.test(d))
      return "Enter a valid US phone number";
    return "";
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatPhoneNumber(e.target.value);
    setPhoneNumber(formatted);
    if (touched) setError(validate(formatted));
  };

  const handleBlur = () => {
    setTouched(true);
    setError(validate(phoneNumber));
  };

  const handleSubmit = () => {
    setTouched(true);
    const msg = validate(phoneNumber);
    setError(msg);
    if (msg) return;

    // do something here
    console.log(digits);
  };

  return (
    <div className="flex flex-col flex-1 items-center justify-center font-sans">
      <h1 className={`${amatic.className} text-7xl font-light pb-5`}>Whatever the app name is</h1>

      <div className="bg-fuchsia-50 p-7 rounded-lg">
        <h1 className="text-3xl font-bold">
          To start, enter your phone number below
        </h1>

        <div className="flex flex-col items-center gap-1 pt-5">
          <div className="flex flex-row gap-2">
            <input
              type="tel"
              inputMode="numeric"
              placeholder="(555) 555-5555"
              className={`border-2 rounded-md p-2 outline-none transition-colors duration-300 hover:shadow-sm ${
                error && touched
                  ? "border-red-400 focus:border-red-500"
                  : "border-gray-300 focus:border-blue-400"
              }`}
              value={phoneNumber}
              onChange={handleChange}
              onBlur={handleBlur}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
            <button
              className="bg-rose-600 text-white p-3 rounded-md hover:bg-rose-800 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleSubmit}
              disabled={touched && !!error}
            >
              Submit
            </button>
          </div>
          {touched && error && (
            <p className="text-red-500 text-sm mt-1">{error}</p>
          )}
        </div>
      </div>
    </div>
  );
}
