/** How the photos picked for one upload become receipts. Photos stay in the order picked; a photo
 * marked "same receipt as the one before" joins the previous photo's receipt (a long receipt shot
 * in two halves). The server takes the result as `groups`: photo indices per receipt. */
export function groupsFrom(joinsPrevious: boolean[]): number[][] {
  const groups: number[][] = [];
  joinsPrevious.forEach((joins, index) => {
    if (joins && index > 0 && groups.length) groups[groups.length - 1].push(index);
    else groups.push([index]);
  });
  return groups;
}

/** At most this many photos make one receipt (the server's limit). */
export const MAX_PHOTOS_PER_RECEIPT = 10;
export const MAX_PHOTOS_PER_UPLOAD = 20;
