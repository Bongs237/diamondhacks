import { Amatic_SC } from "next/font/google";

const amatic = Amatic_SC({
  subsets: ["latin"],
  weight: ["400", "700"],
});

export default function Done() {
  return (
    <div className="flex flex-col flex-1 justify-center items-center font-sans py-10 text-center bg-neutral-900 text-zinc-100 px-4 min-h-full">
      <h1 className={`${amatic.className} text-7xl font-light pb-7 text-zinc-50`}>
        Submitted!
      </h1>
      <p className="text-lg text-zinc-400">
        The organizer will be notified of the new event.
      </p>
    </div>
  );
}
