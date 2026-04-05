"use client";

import { useEffect, useState } from "react";
import { Amatic_SC } from "next/font/google";
import { useRouter } from "next/navigation";
import { SpinnerIcon } from "@/components/SpinnerIcon";
import { GroupData } from "@/utils/types";
import { Users, Calendar, ChevronRight, LogOut } from "lucide-react";

const amatic = Amatic_SC({
  subsets: ["latin"],
  weight: ["400", "700"],
});

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  collecting: { text: "Waiting for people", color: "bg-amber-100 text-amber-800" },
  voting: { text: "Voting", color: "bg-blue-100 text-blue-800" },
  discovery: { text: "Finding events", color: "bg-purple-100 text-purple-800" },
  committed: { text: "Committed", color: "bg-green-100 text-green-800" },
  purchased: { text: "Tickets purchased", color: "bg-green-200 text-green-900" },
  cancelled: { text: "Cancelled", color: "bg-red-100 text-red-800" },
  unknown: { text: "Unknown", color: "bg-gray-100 text-gray-600" },
};

export default function Home() {
  const [groups, setGroups] = useState<GroupData[]>([]);
  const [loading, setLoading] = useState(true);
  const [droppingOut, setDroppingOut] = useState<string | null>(null);
  const router = useRouter();

  const fetchGroups = () => {
    const userId = localStorage.getItem("user_id")!;
    fetch(`/api/user/${userId}/groups`)
      .then((res) => res.json())
      .then((data) => {
        setGroups(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    if (!localStorage.getItem("user_id")) {
      localStorage.setItem("user_id", crypto.randomUUID());
    }
    fetchGroups();
  }, []);

  const handleDropout = async (e: React.MouseEvent, groupId: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to drop out of this event?")) return;

    const userId = localStorage.getItem("user_id")!;
    setDroppingOut(groupId);
    try {
      const res = await fetch(`/api/dropout/${groupId}/${userId}`, {
        method: "POST",
      });
      if (res.ok) {
        setGroups((prev) => prev.filter((g) => g.group_id !== groupId));
      }
    } finally {
      setDroppingOut(null);
    }
  };

  const statusBadge = (status: string) => {
    const s = STATUS_LABELS[status] ?? STATUS_LABELS.unknown;
    return (
      <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${s.color}`}>
        {s.text}
      </span>
    );
  };

  return (
    <div className="flex flex-col flex-1 items-center font-sans py-10 px-4">
      <h1 className={`${amatic.className} text-7xl font-light text-center`}> {/* It's peanut butter ai slop time. I'm so tired that I don't even wanna do this smh */}
        What to Meet
      </h1>
      <h2 className="text-gray-500 py-8 text-2xl font-semibold">Your events</h2>

      {loading ? (
        <div className="flex items-center gap-2 text-gray-500 py-20">
          <SpinnerIcon />
          Loading your events…
        </div>
      ) : groups.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-20 text-center">
          <Calendar className="h-16 w-16 text-gray-300" />
          <p className="text-gray-500 text-lg">No events yet</p>
          <p className="text-gray-400 text-sm max-w-sm">
            Join an event using a link from a friend; it'll show up here.
          </p>
        </div>
      ) : (
        <div className="w-full max-w-2xl flex flex-col gap-4">
          {groups.map((group) => {
            const myName = group.members.find(
              (m: any) => m.user_id === localStorage.getItem("user_id")
            )?.name;
            const otherMembers = group.members
              .filter((m: any) => m.user_id !== localStorage.getItem("user_id"))
              .map((m) => m.name);

            return (
              <button
                key={group.group_id}
                onClick={() => router.push(`/dashboard/${group.group_id}`)}
                className="bg-fuchsia-50 rounded-lg p-5 flex items-center gap-4 hover:bg-fuchsia-100 transition-colors cursor-pointer text-left w-full"
              >
                <div className="bg-rose-100 rounded-full p-3 shrink-0">
                  <Users className="h-6 w-6 text-rose-600" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-lg truncate">
                      Event {group.group_id}
                    </span>
                    {statusBadge(group.status)}
                  </div>

                  <p className="text-gray-500 text-sm mt-1 truncate">
                    {myName ? `You (${myName})` : "You"}
                    {otherMembers.length > 0 && (
                      <> &middot; {otherMembers.join(", ")}</>
                    )}
                  </p>

                  <p className="text-gray-400 text-xs mt-1">
                    {group.member_count} member{group.member_count !== 1 && "s"}
                    {group.vote_result && (
                      <> &middot; Winner: {group.vote_result}</>
                    )}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={(e) => handleDropout(e, group.group_id)}
                    disabled={droppingOut === group.group_id}
                    className="p-2 rounded-full text-gray-400 hover:bg-red-100 hover:text-red-600 transition-colors disabled:opacity-50 cursor-pointer"
                    title="Drop out"
                  >
                    {droppingOut === group.group_id ? (
                      <SpinnerIcon className="h-5 w-5" />
                    ) : (
                      <LogOut className="h-5 w-5" />
                    )}
                  </button>
                  <ChevronRight className="h-5 w-5 text-gray-400" />
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
