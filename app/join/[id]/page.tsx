"use client";

import { useState, useCallback, useEffect } from "react";
import { DM_Sans } from "next/font/google";
import { useParams, useRouter } from "next/navigation";
import { SpinnerIcon } from "@/components/SpinnerIcon";
import { Field } from "@/utils/types";
import { MapPin } from "lucide-react";

const dmSansDisplay = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
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
    label:
      "When are you free? List each day and the time windows that work.",
    placeholder: "e.g. Sat 5–7pm & 8–9pm; Fri 10–11am",
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

function LocationField({
  field,
  locationCity,
  locationLoading,
  locationError,
  touched,
  errors,
  onGetLocation,
}: {
  field: Field;
  locationCity: string;
  locationLoading: boolean;
  locationError: string;
  touched: Record<string, boolean>;
  errors: Record<string, string>;
  onGetLocation: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={onGetLocation}
        disabled={locationLoading}
        className="flex items-center justify-center gap-2 border-2 border-dashed border-neutral-600 rounded-md p-3 text-zinc-300 bg-neutral-900 hover:border-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {locationLoading ? (
          <>
            <SpinnerIcon />
            Getting location...
          </>
        ) : (
          <>
            <MapPin />
            {locationCity ? "Update my location" : "Get my location"}
          </>
        )}
      </button>
      {locationCity && (
        <p className="text-sm text-emerald-400 font-medium text-center">
          {locationCity}
        </p>
      )}
      {locationError && (
        <p className="text-red-400 text-sm">{locationError}</p>
      )}
      {touched[field.key] && errors[field.key] && !locationError && (
        <p className="text-red-400 text-sm">{errors[field.key]}</p>
      )}
    </div>
  );
}

function TextField({
  field,
  value,
  touched,
  error,
  onChange,
  onBlur,
}: {
  field: Field;
  value: string;
  touched: boolean;
  error: string;
  onChange: (key: string, value: string) => void;
  onBlur: (key: string) => void;
}) {
  return (
    <>
      <input
        type={field.type}
        placeholder={field.placeholder}
        className={`border-2 rounded-md p-2 outline-none transition-colors duration-300 bg-neutral-900 text-zinc-100 placeholder:text-zinc-500 hover:shadow-sm ${
          error && touched
            ? "border-red-500 focus:border-red-400"
            : "border-neutral-600 focus:border-zinc-400"
        }`}
        value={value}
        onChange={(e) => onChange(field.key, e.target.value)}
        onBlur={() => onBlur(field.key)}
      />
      {touched && error && (
        <p className="text-red-400 text-sm">{error}</p>
      )}
    </>
  );
}

function emptyValues(): Record<string, unknown> {
  return Object.fromEntries(
    FIELDS.map((f) => [f.key, f.key === "location" ? [] : ""])
  );
}

export default function Join() {
  const [values, setValues] = useState<Record<string, unknown>>(emptyValues);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [locationCity, setLocationCity] = useState<string>("");
  const [locationLoading, setLocationLoading] = useState(false);
  const [locationError, setLocationError] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const params = useParams();
  const groupId = Array.isArray(params.id) ? params.id[0] : params.id;
  const router = useRouter();

  useEffect(() => {
    // Add user id thru local storage
    // wait you can pretend to be anyone if you can just set the local storage bruh
    if (!localStorage.getItem("user_id")) {
      localStorage.setItem("user_id", crypto.randomUUID());
    }
  }, []);

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

  const handleChange = (key: string, raw: string) => {
    setSubmitError("");
    setValues((prev) => ({ ...prev, [key]: raw }));
    if (touched[key]) {
      const field = FIELDS.find((f) => f.key === key)!;
      setErrors((prev) => ({ ...prev, [key]: field.validate(raw) }));
    }
  };

  const handleBlur = (key: string) => {
    setTouched((prev) => ({ ...prev, [key]: true }));
    const field = FIELDS.find((f) => f.key === key)!;
    setErrors((prev) => ({
      ...prev,
      [key]: field.validate(values[key] as never),
    }));
  };

  const handleSubmit = async () => {
    setSubmitError("");
    if (!localStorage.getItem("user_id")) {
      localStorage.setItem("user_id", crypto.randomUUID());
    }
    const userId = localStorage.getItem("user_id")!;

    if (!groupId) {
      setSubmitError("Invalid invite link (missing group id).");
      return;
    }

    const newTouched: Record<string, boolean> = {};
    const newErrors: Record<string, string> = {};
    let hasError = false;

    for (const field of FIELDS) {
      newTouched[field.key] = true;
      const msg = field.validate(values[field.key] as never);
      newErrors[field.key] = msg;
      if (msg) hasError = true;
    }

    setTouched(newTouched);
    setErrors(newErrors);
    if (hasError) return;

    setSubmitting(true);

    const location = Array.isArray(values.location)
      ? values.location
      : [];
    const body = {
      name: String(values.name ?? ""),
      budget: String(values.budget ?? ""),
      likes: String(values.likes ?? ""),
      dislikes: String(values.dislikes ?? ""),
      available_times: String(values.available_times ?? ""),
      distance: String(values.distance ?? ""),
      location,
      user_id: userId,
    };

    try {
      const response = await fetch(
        `/api/submit/${encodeURIComponent(groupId)}`,
        {
          method: "POST",
          body: JSON.stringify(body),
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const d = (data as { detail?: unknown }).detail;
        const msg =
          typeof d === "string"
            ? d
            : response.status === 404
              ? "Group not found — ask the organizer for a fresh link or create the group first."
              : "Could not save your answers. Is the backend running on port 8000?";
        throw new Error(msg);
      }
      if ((data as { error?: string }).error) {
        throw new Error((data as { error: string }).error);
      }

      router.push(`/done`);
    } catch (e) {
      setSubmitError(
        e instanceof Error ? e.message : "Something went wrong. Try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col flex-1 w-full items-center font-sans py-10 px-4 bg-neutral-900 text-zinc-100 min-h-full">
      <h1
        className={`${dmSansDisplay.className} text-7xl font-semibold pb-7 text-center tracking-tight text-zinc-50`}
      >
        What to Meet
      </h1>

      <p className="text-center text-zinc-400 pb-2 max-w-lg px-4">
        Tell us your name, preferences, and location so the group can plan your event.
      </p>
      <div className="bg-neutral-800 p-7 rounded-lg border border-neutral-700 shadow-lg md:min-w-[550px] lg:min-w-[760px] mt-2">
        <div className="flex flex-col gap-5">
          {FIELDS.map((field) => (
            <div key={field.key} className="flex flex-col gap-1">
              <label className="text-lg font-bold text-zinc-100">
                {field.label}
                <span className="font-normal text-red-400 ml-1">*</span>
              </label>
              {field.type === "location" ? (
                <LocationField
                  field={field}
                  locationCity={locationCity}
                  locationLoading={locationLoading}
                  locationError={locationError}
                  touched={touched}
                  errors={errors}
                  onGetLocation={handleGetLocation}
                />
              ) : (
                <TextField
                  field={field}
                  value={
                    typeof values[field.key] === "string"
                      ? (values[field.key] as string)
                      : ""
                  }
                  touched={!!touched[field.key]}
                  error={errors[field.key] || ""}
                  onChange={handleChange}
                  onBlur={handleBlur}
                />
              )}
            </div>
          ))}
        </div>

        {submitError ? (
          <p className="text-red-400 text-sm mt-4 text-center" role="alert">
            {submitError}
          </p>
        ) : null}

        <div className="pt-5 flex justify-center">
          <button
            type="button"
            disabled={submitting}
            className="flex items-center justify-center gap-2 bg-zinc-100 text-neutral-900 px-6 py-3 rounded-md hover:bg-white transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
            onClick={handleSubmit}
          >
            {submitting ? (
              <>
                <SpinnerIcon />
                Submitting…
              </>
            ) : (
              "Submit"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
