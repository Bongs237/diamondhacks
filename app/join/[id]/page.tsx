"use client";

import { useState, useCallback } from "react";
import { Amatic_SC } from "next/font/google";
import { useParams } from "next/navigation";
import { Field } from "@/utils/types";

const amatic = Amatic_SC({
  subsets: ["latin"],
  weight: ["400", "700"],
});

// Data driven type stuff ong fr
// When form submitted each key is json key, value is what you put in the form
const FIELDS: Field[] = [
  {
    key: "name",
    label: "What's your name?",
    placeholder: "Name",
    type: "text",
    required: true,
    validate: (v: string) => (v.trim().length === 0 ? "Name is required" : ""),
  },
  {
    key: "budget",
    label: "What's your budget?",
    placeholder: "$20 - $50, flexible, etc.",
    type: "text",
    required: false,
    validate: () => "",
  },
  {
    key: "likes",
    label: "What do you like?",
    placeholder: "Comedy, live music, etc.",
    type: "text",
    required: false,
    validate: () => "",
  },
  {
    key: "dislikes",
    label: "What do you dislike?",
    placeholder: "Improv, etc.",
    type: "text",
    required: false,
    validate: () => "",
  },
  {
    key: "available_times",
    label: "What times are you available?",
    placeholder: "Saturday evening, Friday night, etc.",
    type: "text",
    required: false,
    validate: () => "",
  },
  {
    key: "distance",
    label: "What's your max travel distance?",
    placeholder: "5-10 miles",
    type: "text",
    required: false,
    validate: () => "",
  },
  {
    key: "location",
    label: "Where are you?",
    type: "location",
    required: true,
    placeholder: undefined,
    validate: (v: number[]) => (v.length === 0 ? "Location is required" : ""),
  }
];

export default function Join() {
  const [values, setValues] = useState<Record<string, any>>(
    Object.fromEntries(FIELDS.map((f) => [f.key, ""]))
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [locationCity, setLocationCity] = useState<string>("");
  const [locationLoading, setLocationLoading] = useState(false);
  const [locationError, setLocationError] = useState<string>("");

  const { id } = useParams();

  const handleGetLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationError("Geolocation is not supported by your browser");
      return;
    }
    setLocationLoading(true);
    setLocationError("");

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setValues((prev) => ({ ...prev, location: [latitude, longitude] }));

        setTouched((prev) => ({ ...prev, location: true }));
        setErrors((prev) => ({ ...prev, location: "" }));
        try {
          // Use openstreetmap to get the actual location names
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json`,
            { headers: { "Accept-Language": "en" } }
          );
          const data = await res.json();
          const city =
            data.address?.city ||
            data.address?.town ||
            data.address?.village ||
            data.address?.county ||
            "Unknown location";
          const state = data.address?.state || "";
          setLocationCity(state ? `${city}, ${state}` : city);
        } catch {
          setLocationCity(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
        }
        setLocationLoading(false);
      },
      (err) => {
        setLocationLoading(false);
        setLocationError(
          err.code === err.PERMISSION_DENIED
            ? "Location permission denied"
            : "Unable to get your location"
        );
      },
      { enableHighAccuracy: false, timeout: 10000 }
    );
  }, []);

  const handleChange = (key: string, raw: any) => {
    setValues((prev) => ({ ...prev, [key]: raw }));
    if (touched[key]) {
      const field = FIELDS.find((f) => f.key === key)!;
      setErrors((prev) => ({ ...prev, [key]: field.validate(raw) }));
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

    const response = await fetch(`/api/submit/${id}`, {
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
              <label className="text-lg font-bold">
                {field.label}
                {field.required && <span className="text-sm font-normal text-red-500 ml-1">*</span>}
              </label>
              {field.type === "location" ? (
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={handleGetLocation}
                    disabled={locationLoading}
                    className="flex items-center justify-center gap-2 border-2 border-dashed border-gray-300 rounded-md p-3 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {locationLoading ? (
                      <>
                        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Getting location...
                      </>
                    ) : (
                      <>
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                        </svg>
                        {locationCity ? "Update my location" : "Get my location"}
                      </>
                    )}
                  </button>
                  {locationCity && (
                    <p className="text-sm text-green-700 font-medium text-center">
                      {locationCity}
                    </p>
                  )}
                  {locationError && (
                    <p className="text-red-500 text-sm">{locationError}</p>
                  )}
                  {touched[field.key] && errors[field.key] && !locationError && (
                    <p className="text-red-500 text-sm">{errors[field.key]}</p>
                  )}
                </div>
              ) : (
                <>
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
                </>
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
