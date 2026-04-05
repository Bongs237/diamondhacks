"use client";

import { useState } from "react";
import { Amatic_SC } from "next/font/google";
import router from "next/router";
import { useParams } from "next/navigation";

const amatic = Amatic_SC({
  subsets: ["latin"],
  weight: ["400", "700"],
});

const FIELDS = [
  {
    key: "name",
    label: "What's your name?",
    placeholder: "Name",
    type: "text" as const,
    validate: (v: string) => (v.trim().length === 0 ? "Name is required" : ""),
  },
  {
    key: "budget",
    label: "What's your budget?",
    placeholder: "$20 - $50, flexible, etc.",
    type: "text" as const,
    validate: (v: string) => (v.length === 0 ? "Budget is required" : ""),
  },
  {
    key: "likes",
    label: "What do you like?",
    placeholder: "Comedy, live music, etc.",
    type: "text" as const,
    validate: (v: string) => (v.length === 0 ? "Likes are required" : ""),
  },
  {
    key: "dislikes",
    label: "What do you dislike?",
    placeholder: "Improv, etc.",
    type: "text" as const,
    validate: (v: string) => (v.length === 0 ? "Dislikes are required" : ""),
  },
  {
    key: "available_times",
    label: "What times are you available?",
    placeholder: "Saturday evening, Friday night, etc.",
    type: "text" as const,
    validate: (v: string) => (v.length === 0 ? "Available times are required" : ""),
  },
  {
    key: "max_transit_min",
    label: "What's your max transit time?",
    placeholder: "30 minutes, 1 hour, etc.",
    type: "text" as const,
    validate: (v: string) => (v.length === 0 ? "Max transit time is required" : ""),
  },
];

export default function Join() {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(FIELDS.map((f) => [f.key, ""]))
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const { id } = useParams();

  const handleChange = (key: string, raw: string) => {
    let val = raw;
    setValues((prev) => ({ ...prev, [key]: val }));
    if (touched[key]) {
      const field = FIELDS.find((f) => f.key === key)!;
      setErrors((prev) => ({ ...prev, [key]: field.validate(val) }));
    }
  };

  const handleBlur = (key: string) => {
    setTouched((prev) => ({ ...prev, [key]: true }));
    const field = FIELDS.find((f) => f.key === key)!;
    setErrors((prev) => ({ ...prev, [key]: field.validate(values[key]) }));
  };

  const handleSubmit = async () => {
    const newTouched: Record<string, boolean> = {};
    const newErrors: Record<string, string> = {};
    let hasError = false;

    for (const field of FIELDS) {
      newTouched[field.key] = true;
      const msg = field.validate(values[field.key]);
      newErrors[field.key] = msg;
      if (msg) hasError = true;
    }

    setTouched(newTouched);
    setErrors(newErrors);
    if (hasError) return;

    // Do the thing
    const response = await fetch(`/api/whatever/${id}`, {
      method: "POST",
      body: JSON.stringify(values),
    });

    if (!response.ok) {
      throw new Error("Failed to join event");
    }
    
    const data = await response.json();
    if (data.error) {
      throw new Error(data.error);
    }
  };

  return (
    <div className="flex flex-col flex-1 items-center font-sans py-10">
      <h1 className={`${amatic.className} text-7xl font-light pb-7 text-center`}> {/* 7 is my lucky number */}
        What to Meet or whatever
      </h1>

      <p className="text-center text-gray-500 pb-5 font-semibold"><strong>Note:</strong> All fields are free response!</p>

      <div className="bg-fuchsia-50 p-7 rounded-lg min-w-[360px]">
        <div className="flex flex-col gap-5">
          {FIELDS.map((field) => (
            <div key={field.key} className="flex flex-col gap-1">
              <label className="text-lg font-bold">{field.label}</label>
              <input
                type={field.type}
                placeholder={field.placeholder}
                className={`border-2 rounded-md p-2 outline-none transition-colors duration-300 hover:shadow-sm ${
                  errors[field.key] && touched[field.key]
                    ? "border-red-400 focus:border-red-500"
                    : "border-gray-300 focus:border-blue-400"
                }`}
                value={values[field.key]}
                onChange={(e) => handleChange(field.key, e.target.value)}
                onBlur={() => handleBlur(field.key)}
              />
              {touched[field.key] && errors[field.key] && (
                <p className="text-red-500 text-sm">{errors[field.key]}</p>
              )}
            </div>
          ))}
        </div>

        <div className="pt-5 flex justify-center">
          <button
            className="bg-rose-600 text-white px-6 py-3 rounded-md hover:bg-rose-800 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={handleSubmit}
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
